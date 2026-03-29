package device

import (
	"context"
	"crypto/md5"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/bassrock/onvif-splitter/internal/config"
	"github.com/bassrock/onvif-splitter/internal/discovery"
	"github.com/bassrock/onvif-splitter/internal/proxy"
	"github.com/bassrock/onvif-splitter/internal/soap"
)

type VirtualDevice struct {
	Channel config.ChannelConfig
	Config  *config.Config
	server  *http.Server

	mu            sync.Mutex
	subscriptions map[string]*Subscription
}

type Subscription struct {
	ID      string
	Events  chan string
	Created time.Time
	TTL     time.Duration
}

func New(ch config.ChannelConfig, cfg *config.Config) (*VirtualDevice, error) {
	return &VirtualDevice{
		Channel:       ch,
		Config:        cfg,
		subscriptions: make(map[string]*Subscription),
	}, nil
}

func (d *VirtualDevice) Name() string { return d.Channel.Name }
func (d *VirtualDevice) IP() string   { return d.Channel.IP }

func (d *VirtualDevice) ServiceURL(path string) string {
	return fmt.Sprintf("http://%s:%d%s", d.Channel.IP, d.Channel.Port, path)
}

func (d *VirtualDevice) RTSPURL(subtype int) string {
	return fmt.Sprintf("rtsp://%s:%d/cam/realmonitor?channel=%d&amp;subtype=%d&amp;unicast=true&amp;proto=Onvif",
		d.Config.NVR.Host, d.Config.NVR.RTSPPort, d.Channel.Channel, subtype)
}

func (d *VirtualDevice) Start(ctx context.Context) error {
	mux := http.NewServeMux()
	mux.HandleFunc("/onvif/device_service", d.handleSOAP)
	mux.HandleFunc("/onvif/media_service", d.handleSOAP)
	mux.HandleFunc("/onvif/event_service", d.handleSOAP)
	mux.HandleFunc("/onvif/subscription/", d.handleSOAP)
	mux.HandleFunc("/onvif/snapshot", d.handleSnapshot)
	mux.HandleFunc("/internal/event", d.handleEventPush)

	addr := fmt.Sprintf("%s:%d", d.Channel.IP, d.Channel.Port)
	d.server = &http.Server{Addr: addr, Handler: mux}

	go func() {
		if err := d.server.ListenAndServe(); err != http.ErrServerClosed {
			log.Printf("HTTP server error for %s: %v", d.Name(), err)
		}
	}()

	log.Printf("Virtual device %s (ch%d) listening on %s", d.Name(), d.Channel.Channel, addr)

	// Start RTSP proxy
	rtspLocal := fmt.Sprintf("%s:554", d.Channel.IP)
	rtspRemote := fmt.Sprintf("%s:%d", d.Config.NVR.Host, d.Config.NVR.RTSPPort)
	if err := proxy.StartRTSP(ctx, rtspLocal, rtspRemote); err != nil {
		log.Printf("Warning: RTSP proxy failed for %s: %v", d.Name(), err)
	}

	// Start WS-Discovery
	disc := discovery.Device{
		UUID: d.Channel.DeviceUUID,
		Name: d.Channel.Name,
		IP:   d.Channel.IP,
		Port: d.Channel.Port,
	}
	if err := discovery.Start(ctx, disc); err != nil {
		log.Printf("Warning: WS-Discovery failed for %s: %v", d.Name(), err)
	}

	return nil
}

func (d *VirtualDevice) Stop() {
	if d.server != nil {
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		d.server.Shutdown(ctx)
	}
}

func (d *VirtualDevice) PushEvent(eventXML string) {
	d.mu.Lock()
	defer d.mu.Unlock()
	pushed := 0
	for id, sub := range d.subscriptions {
		if time.Since(sub.Created) > sub.TTL+30*time.Second {
			delete(d.subscriptions, id)
			continue
		}
		select {
		case sub.Events <- eventXML:
			pushed++
		default: // drop if full
		}
	}
	if pushed > 0 {
		log.Printf("Pushed event to %d subscription(s) on %s", pushed, d.Name())
	}
}

func (d *VirtualDevice) handleSOAP(w http.ResponseWriter, r *http.Request) {
	body, err := soap.ReadBody(r)
	if err != nil {
		soap.WriteFault(w, "sender", "InvalidXML", "Could not read request", 400)
		return
	}

	action := soap.ParseAction(extractBodyInner(body))
	if action == "" {
		soap.WriteFault(w, "sender", "EmptyBody", "No action found", 400)
		return
	}

	// Unauthenticated actions
	if action == "GetSystemDateAndTime" {
		d.getSystemDateAndTime(w)
		return
	}

	// Subscription endpoints — the subscription ID itself is the auth token
	path := r.URL.Path
	if strings.HasPrefix(path, "/onvif/subscription/") {
		subID := strings.TrimPrefix(path, "/onvif/subscription/")
		switch action {
		case "PullMessages":
			d.pullMessages(w, body, subID)
		case "Renew":
			d.renew(w, subID)
		case "Unsubscribe":
			d.unsubscribe(w, subID)
		default:
			soap.WriteFault(w, "sender", "ActionNotSupported", "Unknown action", 400)
		}
		return
	}

	// Check auth for all other actions
	if !soap.ValidateAuthFlexible(body, d.Config.NVR.Username, d.Config.NVR.Password) {
		soap.WriteFault(w, "sender", "NotAuthorized", "Authentication failed", 401)
		return
	}

	switch action {
	case "GetDeviceInformation":
		d.getDeviceInformation(w)
	case "GetServices":
		d.getServices(w)
	case "GetCapabilities":
		d.getCapabilities(w)
	case "GetScopes":
		d.getScopes(w)
	case "GetNetworkInterfaces":
		d.getNetworkInterfaces(w)
	case "GetProfiles":
		d.getProfiles(w)
	case "GetProfile":
		d.getProfiles(w) // simplified
	case "GetStreamUri":
		d.getStreamURI(w, body)
	case "GetSnapshotUri":
		d.getSnapshotURI(w)
	case "GetVideoSources":
		d.getVideoSources(w)
	case "GetVideoSourceConfigurations":
		d.getVideoSourceConfigurations(w)
	case "GetEventProperties":
		d.getEventProperties(w)
	case "GetServiceCapabilities":
		d.getEventServiceCapabilities(w)
	case "CreatePullPointSubscription":
		d.createPullPointSubscription(w)
	case "Subscribe":
		d.createPullPointSubscription(w)
	default:
		soap.WriteFault(w, "sender", "ActionNotSupported", fmt.Sprintf("Action %s not supported", action), 400)
	}
}

func (d *VirtualDevice) handleSnapshot(w http.ResponseWriter, r *http.Request) {
	uri := fmt.Sprintf("/cgi-bin/snapshot.cgi?channel=%d", d.Channel.Channel)
	url := fmt.Sprintf("http://%s:%d%s", d.Config.NVR.Host, d.Config.NVR.Port, uri)

	// Use a transport that doesn't reuse connections (avoids auth state issues)
	client := &http.Client{
		Timeout:   10 * time.Second,
		Transport: &http.Transport{DisableKeepAlives: true},
	}

	// First request without auth to get digest challenge
	req, _ := http.NewRequest("GET", url, nil)
	resp, err := client.Do(req)
	if err != nil {
		http.Error(w, "Snapshot failed", 502)
		return
	}

	if resp.StatusCode == 200 {
		w.Header().Set("Content-Type", resp.Header.Get("Content-Type"))
		io.Copy(w, resp.Body)
		resp.Body.Close()
		return
	}

	wwwAuth := resp.Header.Get("WWW-Authenticate")
	resp.Body.Close()

	if resp.StatusCode == 401 && strings.Contains(wwwAuth, "Digest") {
		authHeader := computeDigestAuth(wwwAuth, "GET", uri,
			d.Config.NVR.Username, d.Config.NVR.Password)
		req2, _ := http.NewRequest("GET", url, nil)
		req2.Header.Set("Authorization", authHeader)
		resp2, err := client.Do(req2)
		if err != nil {
			http.Error(w, "Snapshot failed", 502)
			return
		}
		defer resp2.Body.Close()
		if resp2.StatusCode == 200 {
			w.Header().Set("Content-Type", resp2.Header.Get("Content-Type"))
			io.Copy(w, resp2.Body)
			return
		}
		log.Printf("Snapshot digest auth failed: %d", resp2.StatusCode)
	}

	http.Error(w, "Snapshot failed", 502)
}

func computeDigestAuth(wwwAuth, method, uri, username, password string) string {
	params := map[string]string{}
	for _, match := range regexp.MustCompile(`(\w+)="([^"]*)"`) .FindAllStringSubmatch(wwwAuth, -1) {
		params[match[1]] = match[2]
	}
	realm := params["realm"]
	nonce := params["nonce"]
	qop := params["qop"]

	ha1 := md5Hash(fmt.Sprintf("%s:%s:%s", username, realm, password))
	ha2 := md5Hash(fmt.Sprintf("%s:%s", method, uri))

	if strings.Contains(qop, "auth") {
		nc := "00000001"
		cnonce := fmt.Sprintf("%08x", time.Now().UnixNano())
		response := md5Hash(fmt.Sprintf("%s:%s:%s:%s:auth:%s", ha1, nonce, nc, cnonce, ha2))
		return fmt.Sprintf(`Digest username="%s", realm="%s", nonce="%s", uri="%s", qop=auth, nc=%s, cnonce="%s", response="%s"`,
			username, realm, nonce, uri, nc, cnonce, response)
	}
	response := md5Hash(fmt.Sprintf("%s:%s:%s", ha1, nonce, ha2))
	return fmt.Sprintf(`Digest username="%s", realm="%s", nonce="%s", uri="%s", response="%s"`,
		username, realm, nonce, uri, response)
}

func md5Hash(s string) string {
	h := md5.Sum([]byte(s))
	return fmt.Sprintf("%x", h)
}

func (d *VirtualDevice) handleEventPush(w http.ResponseWriter, r *http.Request) {
	body, _ := io.ReadAll(r.Body)
	r.Body.Close()
	d.PushEvent(string(body))
	w.Write([]byte("ok"))
}

func extractBodyInner(xmlBytes []byte) []byte {
	s := string(xmlBytes)
	// Find <s:Body> or <Body> content
	for _, tag := range []string{"Body>", "body>"} {
		idx := strings.Index(s, tag)
		if idx >= 0 {
			start := idx + len(tag)
			endTag := "</" + s[idx-2:idx] + tag
			end := strings.Index(s[start:], endTag)
			if end < 0 {
				end = strings.LastIndex(s, "</")
			}
			if end >= 0 {
				return []byte(s[start : start+end])
			}
		}
	}
	return xmlBytes
}
