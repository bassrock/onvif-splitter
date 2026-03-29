package events

import (
	"bytes"
	"context"
	"crypto/sha1"
	"encoding/base64"
	"crypto/rand"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/bassrock/onvif-splitter/internal/config"
	"github.com/bassrock/onvif-splitter/internal/device"
)

var (
	tokenToChannel = map[string]int{}
	reSource       = regexp.MustCompile(`Name="VideoSourceConfigurationToken"\s+Value="([^"]+)"`)
	reIsMotion     = regexp.MustCompile(`Name="IsMotion"\s+Value="([^"]+)"`)
	reAddress      = regexp.MustCompile(`Address[^>]*>([^<]+)`)
)

func init() {
	for i := 0; i < 16; i++ {
		tokenToChannel[fmt.Sprintf("%05x", i*256)] = i + 1
		tokenToChannel[fmt.Sprintf("%05d", i*100)] = i + 1
	}
}

type Subscriber struct {
	cfg     *config.Config
	devices map[int]*device.VirtualDevice
	client  *http.Client
}

func NewSubscriber(cfg *config.Config, devices map[int]*device.VirtualDevice) *Subscriber {
	return &Subscriber{
		cfg:     cfg,
		devices: devices,
		client:  &http.Client{Timeout: 30 * time.Second},
	}
}

func (s *Subscriber) Run(ctx context.Context) {
	backoff := 5 * time.Second
	for {
		select {
		case <-ctx.Done():
			return
		default:
		}

		err := s.subscribeAndPoll(ctx)
		if err != nil {
			if ctx.Err() != nil {
				return
			}
			log.Printf("NVR event subscriber error: %v, retrying in %v", err, backoff)
			time.Sleep(backoff)
			if backoff < 60*time.Second {
				backoff *= 2
			}
		} else {
			backoff = 5 * time.Second
		}
	}
}

func (s *Subscriber) makeAuth() string {
	nonce := make([]byte, 16)
	rand.Read(nonce)
	created := time.Now().UTC().Format(time.RFC3339)
	h := sha1.New()
	h.Write(nonce)
	h.Write([]byte(created))
	h.Write([]byte(s.cfg.NVR.Password))
	digest := base64.StdEncoding.EncodeToString(h.Sum(nil))
	nonceB64 := base64.StdEncoding.EncodeToString(nonce)

	return fmt.Sprintf(`<wsse:Security xmlns:wsse="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
    xmlns:wsu="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd">
    <wsse:UsernameToken>
      <wsse:Username>%s</wsse:Username>
      <wsse:Password Type="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest">%s</wsse:Password>
      <wsse:Nonce EncodingType="http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary">%s</wsse:Nonce>
      <wsu:Created>%s</wsu:Created>
    </wsse:UsernameToken>
  </wsse:Security>`, s.cfg.NVR.Username, digest, nonceB64, created)
}

func (s *Subscriber) soapCall(url, body string) (string, error) {
	soap := fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
<s:Header>%s</s:Header>
<s:Body>%s</s:Body>
</s:Envelope>`, s.makeAuth(), body)

	req, err := http.NewRequest("POST", url, bytes.NewBufferString(soap))
	if err != nil {
		return "", err
	}
	req.Header.Set("Content-Type", "application/soap+xml")

	resp, err := s.client.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func (s *Subscriber) subscribeAndPoll(ctx context.Context) error {
	eventURL := fmt.Sprintf("http://%s:%d/onvif/event_service", s.cfg.NVR.Host, s.cfg.NVR.Port)

	// Create PullPoint subscription
	resp, err := s.soapCall(eventURL, `<tev:CreatePullPointSubscription xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
    <tev:InitialTerminationTime>PT60S</tev:InitialTerminationTime>
  </tev:CreatePullPointSubscription>`)
	if err != nil {
		return fmt.Errorf("create subscription: %w", err)
	}

	if strings.Contains(resp, "NotAuthorized") || strings.Contains(resp, "Fault") {
		return fmt.Errorf("subscription auth failed")
	}

	match := reAddress.FindStringSubmatch(resp)
	if match == nil {
		return fmt.Errorf("no subscription address in response")
	}
	pullURL := strings.TrimSpace(match[1])
	log.Printf("NVR PullPoint subscription: %s", pullURL)

	// Poll loop
	renewTicker := time.NewTicker(50 * time.Second)
	defer renewTicker.Stop()

	for {
		select {
		case <-ctx.Done():
			return nil
		case <-renewTicker.C:
			s.renewSubscription(pullURL)
		default:
		}

		events, err := s.pullMessages(pullURL)
		if err != nil {
			return fmt.Errorf("pull messages: %w", err)
		}

		for _, evt := range events {
			if dev, ok := s.devices[evt.Channel]; ok {
				dev.PushEvent(makeMotionEventXML(evt.Channel, evt.IsMotion))
				log.Printf("Motion %s on channel %d", boolToStr(evt.IsMotion, "started", "stopped"), evt.Channel)
			}
		}
	}
}

type motionEvent struct {
	Channel  int
	IsMotion bool
}

func (s *Subscriber) pullMessages(url string) ([]motionEvent, error) {
	resp, err := s.soapCall(url, `<tev:PullMessages xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
    <tev:Timeout>PT10S</tev:Timeout>
    <tev:MessageLimit>100</tev:MessageLimit>
  </tev:PullMessages>`)
	if err != nil {
		return nil, err
	}

	return parseEvents(resp), nil
}

func (s *Subscriber) renewSubscription(url string) {
	_, err := s.soapCall(url, `<wsnt:Renew xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
    <wsnt:TerminationTime>PT60S</wsnt:TerminationTime>
  </wsnt:Renew>`)
	if err != nil {
		log.Printf("Subscription renewal failed: %v", err)
	} else {
		log.Printf("Subscription renewed")
	}
}

func parseEvents(xml string) []motionEvent {
	var events []motionEvent

	// Split by Message elements
	parts := strings.Split(xml, "Message")
	for _, part := range parts {
		srcMatch := reSource.FindStringSubmatch(part)
		motionMatch := reIsMotion.FindStringSubmatch(part)

		if srcMatch == nil || motionMatch == nil {
			continue
		}

		token := srcMatch[1]
		isMotion := motionMatch[1] == "true"

		channel := tokenToChannel[token]
		if channel == 0 {
			// Try parsing as hex index * 256
			var idx int
			if _, err := fmt.Sscanf(token, "%x", &idx); err == nil {
				channel = idx/256 + 1
			}
		}

		if channel > 0 {
			events = append(events, motionEvent{Channel: channel, IsMotion: isMotion})
		}
	}

	return events
}

func makeMotionEventXML(channel int, isMotion bool) string {
	now := time.Now().UTC().Format(time.RFC3339)
	val := "false"
	if isMotion {
		val = "true"
	}
	return fmt.Sprintf(`<wsnt:NotificationMessage xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"
    xmlns:tns1="http://www.onvif.org/ver10/topics" xmlns:tt="http://www.onvif.org/ver10/schema">
    <wsnt:Topic Dialect="http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet">tns1:RuleEngine/CellMotionDetector/Motion</wsnt:Topic>
    <wsnt:Message><tt:Message UtcTime="%s" PropertyOperation="Changed">
      <tt:Source><tt:SimpleItem Name="VideoSourceConfigurationToken" Value="VideoSourceConfig_%d"/><tt:SimpleItem Name="VideoAnalyticsConfigurationToken" Value="VideoAnalyticsConfig_%d"/><tt:SimpleItem Name="Rule" Value="MyMotionDetectorRule"/></tt:Source>
      <tt:Data><tt:SimpleItem Name="IsMotion" Value="%s"/></tt:Data>
    </tt:Message></wsnt:Message>
  </wsnt:NotificationMessage>`, now, channel, channel, val)
}

func boolToStr(b bool, t, f string) string {
	if b {
		return t
	}
	return f
}
