package discovery

import (
	"context"
	"fmt"
	"log"
	"net"
	"strings"
	"time"

	"github.com/google/uuid"
)

const (
	multicastAddr = "239.255.255.250:3702"
	onvifTypes    = "dn:NetworkVideoTransmitter"
)

type Device struct {
	UUID string
	Name string
	IP   string
	Port int
}

func Start(ctx context.Context, dev Device) error {
	addr, err := net.ResolveUDPAddr("udp4", multicastAddr)
	if err != nil {
		return err
	}

	iface := findInterface(dev.IP)

	conn, err := net.ListenMulticastUDP("udp4", iface, addr)
	if err != nil {
		// Fallback: listen on specific IP
		localAddr, _ := net.ResolveUDPAddr("udp4", dev.IP+":3702")
		conn, err = net.ListenUDP("udp4", localAddr)
		if err != nil {
			return fmt.Errorf("ws-discovery listen: %w", err)
		}
	}

	log.Printf("WS-Discovery started for %s on %s", dev.Name, dev.IP)

	// Send Hello
	hello := makeHello(dev)
	conn.WriteToUDP([]byte(hello), addr)

	go func() {
		defer conn.Close()
		buf := make([]byte, 65536)
		for {
			select {
			case <-ctx.Done():
				bye := makeBye(dev)
				conn.WriteToUDP([]byte(bye), addr)
				return
			default:
			}

			conn.SetReadDeadline(time.Now().Add(2 * time.Second))
			n, remoteAddr, err := conn.ReadFromUDP(buf)
			if err != nil {
				continue
			}

			data := string(buf[:n])
			if strings.Contains(data, "Probe") && !strings.Contains(data, "ProbeMatch") {
				msgID := extractTag(data, "MessageID")
				resp := makeProbeMatch(dev, msgID)
				conn.WriteToUDP([]byte(resp), remoteAddr)
				log.Printf("WS-Discovery: sent ProbeMatch for %s to %s", dev.Name, remoteAddr)
			}
		}
	}()

	return nil
}

func findInterface(ip string) *net.Interface {
	ifaces, err := net.Interfaces()
	if err != nil {
		return nil
	}
	for _, iface := range ifaces {
		addrs, err := iface.Addrs()
		if err != nil {
			continue
		}
		for _, addr := range addrs {
			if strings.HasPrefix(addr.String(), ip+"/") {
				return &iface
			}
		}
	}
	return nil
}

func extractTag(xml, tag string) string {
	patterns := []string{
		"<wsa:" + tag + ">",
		"<a:" + tag + ">",
	}
	for _, p := range patterns {
		idx := strings.Index(xml, p)
		if idx >= 0 {
			start := idx + len(p)
			end := strings.Index(xml[start:], "</")
			if end >= 0 {
				return strings.TrimSpace(xml[start : start+end])
			}
		}
	}
	return ""
}

func makeHello(dev Device) string {
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<s:Header>
  <wsa:MessageID>urn:uuid:%s</wsa:MessageID>
  <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Hello</wsa:Action>
  <d:AppSequence InstanceId="1" MessageNumber="1"/>
</s:Header>
<s:Body><d:Hello>
  <wsa:EndpointReference><wsa:Address>urn:uuid:%s</wsa:Address></wsa:EndpointReference>
  <d:Types>%s</d:Types>
  <d:Scopes>%s</d:Scopes>
  <d:XAddrs>http://%s:%d/onvif/device_service</d:XAddrs>
  <d:MetadataVersion>1</d:MetadataVersion>
</d:Hello></s:Body></s:Envelope>`,
		uuid.New(), dev.UUID, onvifTypes, scopes(dev), dev.IP, dev.Port)
}

func makeProbeMatch(dev Device, relatesTo string) string {
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"
  xmlns:dn="http://www.onvif.org/ver10/network/wsdl">
<s:Header>
  <wsa:MessageID>urn:uuid:%s</wsa:MessageID>
  <wsa:RelatesTo>%s</wsa:RelatesTo>
  <wsa:To>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:To>
  <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/ProbeMatches</wsa:Action>
  <d:AppSequence InstanceId="1" MessageNumber="1"/>
</s:Header>
<s:Body><d:ProbeMatches><d:ProbeMatch>
  <wsa:EndpointReference><wsa:Address>urn:uuid:%s</wsa:Address></wsa:EndpointReference>
  <d:Types>%s</d:Types>
  <d:Scopes>%s</d:Scopes>
  <d:XAddrs>http://%s:%d/onvif/device_service</d:XAddrs>
  <d:MetadataVersion>1</d:MetadataVersion>
</d:ProbeMatch></d:ProbeMatches></s:Body></s:Envelope>`,
		uuid.New(), relatesTo, dev.UUID, onvifTypes, scopes(dev), dev.IP, dev.Port)
}

func makeBye(dev Device) string {
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
<s:Header>
  <wsa:MessageID>urn:uuid:%s</wsa:MessageID>
  <wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>
  <wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Bye</wsa:Action>
</s:Header>
<s:Body><d:Bye>
  <wsa:EndpointReference><wsa:Address>urn:uuid:%s</wsa:Address></wsa:EndpointReference>
</d:Bye></s:Body></s:Envelope>`, uuid.New(), dev.UUID)
}

func scopes(dev Device) string {
	name := strings.ReplaceAll(dev.Name, " ", "%20")
	return fmt.Sprintf("onvif://www.onvif.org/type/video_encoder onvif://www.onvif.org/type/Network_Video_Transmitter onvif://www.onvif.org/hardware/ONVIF-Splitter onvif://www.onvif.org/name/%s", name)
}
