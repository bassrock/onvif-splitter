package device

import (
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/bassrock/onvif-splitter/internal/soap"
	"github.com/google/uuid"
)

func (d *VirtualDevice) getSystemDateAndTime(w http.ResponseWriter) {
	now := time.Now().UTC()
	soap.WriteSOAP(w, fmt.Sprintf(`
<tds:GetSystemDateAndTimeResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tds:SystemDateAndTime>
    <tt:DateTimeType>NTP</tt:DateTimeType>
    <tt:DaylightSavings>false</tt:DaylightSavings>
    <tt:TimeZone><tt:TZ>UTC0</tt:TZ></tt:TimeZone>
    <tt:UTCDateTime>
      <tt:Time><tt:Hour>%d</tt:Hour><tt:Minute>%d</tt:Minute><tt:Second>%d</tt:Second></tt:Time>
      <tt:Date><tt:Year>%d</tt:Year><tt:Month>%d</tt:Month><tt:Day>%d</tt:Day></tt:Date>
    </tt:UTCDateTime>
  </tds:SystemDateAndTime>
</tds:GetSystemDateAndTimeResponse>`, now.Hour(), now.Minute(), now.Second(), now.Year(), int(now.Month()), now.Day()))
}

func (d *VirtualDevice) getDeviceInformation(w http.ResponseWriter) {
	soap.WriteSOAP(w, fmt.Sprintf(`
<tds:GetDeviceInformationResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl">
  <tds:Manufacturer>ONVIF-Splitter</tds:Manufacturer>
  <tds:Model>Virtual Camera</tds:Model>
  <tds:FirmwareVersion>1.0.0</tds:FirmwareVersion>
  <tds:SerialNumber>ONVIFSPLIT%04d</tds:SerialNumber>
  <tds:HardwareId>ONVIF-SPLIT-%d</tds:HardwareId>
</tds:GetDeviceInformationResponse>`, d.Channel.Channel, d.Channel.Channel))
}

func (d *VirtualDevice) getServices(w http.ResponseWriter) {
	soap.WriteSOAP(w, fmt.Sprintf(`
<tds:GetServicesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tds:Service><tds:Namespace>http://www.onvif.org/ver10/device/wsdl</tds:Namespace><tds:XAddr>%s</tds:XAddr><tds:Version><tt:Major>2</tt:Major><tt:Minor>50</tt:Minor></tds:Version></tds:Service>
  <tds:Service><tds:Namespace>http://www.onvif.org/ver10/media/wsdl</tds:Namespace><tds:XAddr>%s</tds:XAddr><tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version></tds:Service>
  <tds:Service><tds:Namespace>http://www.onvif.org/ver10/events/wsdl</tds:Namespace><tds:XAddr>%s</tds:XAddr><tds:Version><tt:Major>2</tt:Major><tt:Minor>60</tt:Minor></tds:Version></tds:Service>
</tds:GetServicesResponse>`,
		d.ServiceURL("/onvif/device_service"),
		d.ServiceURL("/onvif/media_service"),
		d.ServiceURL("/onvif/event_service")))
}

func (d *VirtualDevice) getCapabilities(w http.ResponseWriter) {
	soap.WriteSOAP(w, fmt.Sprintf(`
<tds:GetCapabilitiesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tds:Capabilities>
    <tt:Device><tt:XAddr>%s</tt:XAddr><tt:Network><tt:IPFilter>false</tt:IPFilter><tt:ZeroConfiguration>false</tt:ZeroConfiguration><tt:IPVersion6>false</tt:IPVersion6><tt:DynDNS>false</tt:DynDNS></tt:Network><tt:System><tt:DiscoveryResolve>false</tt:DiscoveryResolve><tt:DiscoveryBye>true</tt:DiscoveryBye><tt:RemoteDiscovery>false</tt:RemoteDiscovery><tt:SystemBackup>false</tt:SystemBackup><tt:SystemLogging>false</tt:SystemLogging><tt:FirmwareUpgrade>false</tt:FirmwareUpgrade></tt:System><tt:Security><tt:TLS1.1>false</tt:TLS1.1><tt:TLS1.2>false</tt:TLS1.2><tt:OnboardKeyGeneration>false</tt:OnboardKeyGeneration><tt:AccessPolicyConfig>false</tt:AccessPolicyConfig><tt:X.509Token>false</tt:X.509Token><tt:SAMLToken>false</tt:SAMLToken><tt:KerberosToken>false</tt:KerberosToken><tt:RELToken>false</tt:RELToken></tt:Security></tt:Device>
    <tt:Media><tt:XAddr>%s</tt:XAddr><tt:StreamingCapabilities><tt:RTPMulticast>false</tt:RTPMulticast><tt:RTP_TCP>true</tt:RTP_TCP><tt:RTP_RTSP_TCP>true</tt:RTP_RTSP_TCP></tt:StreamingCapabilities></tt:Media>
    <tt:Events><tt:XAddr>%s</tt:XAddr><tt:WSSubscriptionPolicySupport>false</tt:WSSubscriptionPolicySupport><tt:WSPullPointSupport>true</tt:WSPullPointSupport></tt:Events>
  </tds:Capabilities>
</tds:GetCapabilitiesResponse>`,
		d.ServiceURL("/onvif/device_service"),
		d.ServiceURL("/onvif/media_service"),
		d.ServiceURL("/onvif/event_service")))
}

func (d *VirtualDevice) getScopes(w http.ResponseWriter) {
	name := strings.ReplaceAll(d.Channel.Name, " ", "%20")
	soap.WriteSOAP(w, fmt.Sprintf(`
<tds:GetScopesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/type/video_encoder</tt:ScopeItem></tds:Scopes>
  <tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/type/Network_Video_Transmitter</tt:ScopeItem></tds:Scopes>
  <tds:Scopes><tt:ScopeDef>Fixed</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/hardware/ONVIF-Splitter</tt:ScopeItem></tds:Scopes>
  <tds:Scopes><tt:ScopeDef>Configurable</tt:ScopeDef><tt:ScopeItem>onvif://www.onvif.org/name/%s</tt:ScopeItem></tds:Scopes>
</tds:GetScopesResponse>`, name))
}

func (d *VirtualDevice) getNetworkInterfaces(w http.ResponseWriter) {
	mac := d.Channel.MAC
	if mac == "" {
		mac = "00:00:00:00:00:00"
	}
	soap.WriteSOAP(w, fmt.Sprintf(`
<tds:GetNetworkInterfacesResponse xmlns:tds="http://www.onvif.org/ver10/device/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <tds:NetworkInterfaces token="eth0">
    <tt:Enabled>true</tt:Enabled>
    <tt:Info><tt:Name>eth0</tt:Name><tt:HwAddress>%s</tt:HwAddress></tt:Info>
    <tt:IPv4><tt:Enabled>true</tt:Enabled><tt:Config><tt:Manual><tt:Address>%s</tt:Address><tt:PrefixLength>24</tt:PrefixLength></tt:Manual><tt:DHCP>false</tt:DHCP></tt:Config></tt:IPv4>
  </tds:NetworkInterfaces>
</tds:GetNetworkInterfacesResponse>`, mac, d.Channel.IP))
}

func (d *VirtualDevice) getProfiles(w http.ResponseWriter) {
	ch := d.Channel.Channel
	soap.WriteSOAP(w, fmt.Sprintf(`
<trt:GetProfilesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <trt:Profiles token="MainStream_%d" fixed="true">
    <tt:Name>MainStream</tt:Name>
    <tt:VideoSourceConfiguration token="VideoSourceConfig_%d"><tt:Name>VideoSourceConfig</tt:Name><tt:UseCount>2</tt:UseCount><tt:SourceToken>VideoSource_%d</tt:SourceToken><tt:Bounds x="0" y="0" width="1920" height="1080"/></tt:VideoSourceConfiguration>
    <tt:VideoEncoderConfiguration token="VideoEncoder_Main_%d"><tt:Name>MainStream</tt:Name><tt:UseCount>1</tt:UseCount><tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>3840</tt:Width><tt:Height>2160</tt:Height></tt:Resolution><tt:Quality>4</tt:Quality><tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit><tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>4096</tt:BitrateLimit></tt:RateControl><tt:H264><tt:GovLength>15</tt:GovLength><tt:H264Profile>Main</tt:H264Profile></tt:H264><tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address><tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast><tt:SessionTimeout>PT60S</tt:SessionTimeout></tt:VideoEncoderConfiguration>
  </trt:Profiles>
  <trt:Profiles token="SubStream_%d" fixed="true">
    <tt:Name>SubStream</tt:Name>
    <tt:VideoSourceConfiguration token="VideoSourceConfig_%d"><tt:Name>VideoSourceConfig</tt:Name><tt:UseCount>2</tt:UseCount><tt:SourceToken>VideoSource_%d</tt:SourceToken><tt:Bounds x="0" y="0" width="1920" height="1080"/></tt:VideoSourceConfiguration>
    <tt:VideoEncoderConfiguration token="VideoEncoder_Sub_%d"><tt:Name>SubStream</tt:Name><tt:UseCount>1</tt:UseCount><tt:Encoding>H264</tt:Encoding><tt:Resolution><tt:Width>640</tt:Width><tt:Height>480</tt:Height></tt:Resolution><tt:Quality>4</tt:Quality><tt:RateControl><tt:FrameRateLimit>15</tt:FrameRateLimit><tt:EncodingInterval>1</tt:EncodingInterval><tt:BitrateLimit>512</tt:BitrateLimit></tt:RateControl><tt:H264><tt:GovLength>15</tt:GovLength><tt:H264Profile>Main</tt:H264Profile></tt:H264><tt:Multicast><tt:Address><tt:Type>IPv4</tt:Type><tt:IPv4Address>0.0.0.0</tt:IPv4Address></tt:Address><tt:Port>0</tt:Port><tt:TTL>0</tt:TTL><tt:AutoStart>false</tt:AutoStart></tt:Multicast><tt:SessionTimeout>PT60S</tt:SessionTimeout></tt:VideoEncoderConfiguration>
  </trt:Profiles>
</trt:GetProfilesResponse>`, ch, ch, ch, ch, ch, ch, ch, ch))
}

func (d *VirtualDevice) getStreamURI(w http.ResponseWriter, body []byte) {
	subtype := 0
	if strings.Contains(string(body), "Sub") {
		subtype = 1
	}
	soap.WriteSOAP(w, fmt.Sprintf(`
<trt:GetStreamUriResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <trt:MediaUri>
    <tt:Uri>%s</tt:Uri>
    <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
    <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
    <tt:Timeout>PT60S</tt:Timeout>
  </trt:MediaUri>
</trt:GetStreamUriResponse>`, d.RTSPURL(subtype)))
}

func (d *VirtualDevice) getSnapshotURI(w http.ResponseWriter) {
	soap.WriteSOAP(w, fmt.Sprintf(`
<trt:GetSnapshotUriResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <trt:MediaUri>
    <tt:Uri>%s</tt:Uri>
    <tt:InvalidAfterConnect>false</tt:InvalidAfterConnect>
    <tt:InvalidAfterReboot>false</tt:InvalidAfterReboot>
    <tt:Timeout>PT60S</tt:Timeout>
  </trt:MediaUri>
</trt:GetSnapshotUriResponse>`, d.ServiceURL("/onvif/snapshot")))
}

func (d *VirtualDevice) getVideoSources(w http.ResponseWriter) {
	soap.WriteSOAP(w, fmt.Sprintf(`
<trt:GetVideoSourcesResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <trt:VideoSources token="VideoSource_%d"><tt:Framerate>30</tt:Framerate><tt:Resolution><tt:Width>3840</tt:Width><tt:Height>2160</tt:Height></tt:Resolution></trt:VideoSources>
</trt:GetVideoSourcesResponse>`, d.Channel.Channel))
}

func (d *VirtualDevice) getVideoSourceConfigurations(w http.ResponseWriter) {
	soap.WriteSOAP(w, fmt.Sprintf(`
<trt:GetVideoSourceConfigurationsResponse xmlns:trt="http://www.onvif.org/ver10/media/wsdl" xmlns:tt="http://www.onvif.org/ver10/schema">
  <trt:Configurations token="VideoSourceConfig_%d"><tt:Name>VideoSourceConfig</tt:Name><tt:UseCount>2</tt:UseCount><tt:SourceToken>VideoSource_%d</tt:SourceToken><tt:Bounds x="0" y="0" width="1920" height="1080"/></trt:Configurations>
</trt:GetVideoSourceConfigurationsResponse>`, d.Channel.Channel, d.Channel.Channel))
}

func (d *VirtualDevice) getEventProperties(w http.ResponseWriter) {
	soap.WriteSOAP(w, `
<tev:GetEventPropertiesResponse xmlns:tev="http://www.onvif.org/ver10/events/wsdl" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:wstop="http://docs.oasis-open.org/wsn/t-1" xmlns:tns1="http://www.onvif.org/ver10/topics" xmlns:tt="http://www.onvif.org/ver10/schema" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <tev:TopicNamespaceLocation>http://www.onvif.org/onvif/ver10/topics/topicns.xml</tev:TopicNamespaceLocation>
  <wsnt:FixedTopicSet>true</wsnt:FixedTopicSet>
  <wstop:TopicSet><tns1:RuleEngine><CellMotionDetector><Motion wstop:topic="true"><tt:MessageDescription IsProperty="true"><tt:Source><tt:SimpleItemDescription Name="VideoSourceConfigurationToken" Type="tt:ReferenceToken"/><tt:SimpleItemDescription Name="VideoAnalyticsConfigurationToken" Type="tt:ReferenceToken"/><tt:SimpleItemDescription Name="Rule" Type="xs:string"/></tt:Source><tt:Data><tt:SimpleItemDescription Name="IsMotion" Type="xs:boolean"/></tt:Data></tt:MessageDescription></Motion></CellMotionDetector></tns1:RuleEngine></wstop:TopicSet>
  <wsnt:TopicExpressionDialect>http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet</wsnt:TopicExpressionDialect>
</tev:GetEventPropertiesResponse>`)
}

func (d *VirtualDevice) getEventServiceCapabilities(w http.ResponseWriter) {
	soap.WriteSOAP(w, `
<tev:GetServiceCapabilitiesResponse xmlns:tev="http://www.onvif.org/ver10/events/wsdl">
  <tev:Capabilities WSSubscriptionPolicySupport="false" WSPullPointSupport="true" WSPausableSubscriptionManagerInterfaceSupport="false" MaxNotificationProducers="10" MaxPullPoints="10"/>
</tev:GetServiceCapabilitiesResponse>`)
}

func (d *VirtualDevice) createPullPointSubscription(w http.ResponseWriter) {
	subID := uuid.New().String()
	sub := &Subscription{
		ID:      subID,
		Events:  make(chan string, 100),
		Created: time.Now(),
		TTL:     60 * time.Second,
	}

	d.mu.Lock()
	d.subscriptions[subID] = sub
	d.mu.Unlock()

	now := time.Now().UTC()
	term := now.Add(sub.TTL)

	soap.WriteSOAP(w, fmt.Sprintf(`
<tev:CreatePullPointSubscriptionResponse xmlns:tev="http://www.onvif.org/ver10/events/wsdl" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2" xmlns:wsa5="http://www.w3.org/2005/08/addressing">
  <tev:SubscriptionReference><wsa5:Address>%s</wsa5:Address></tev:SubscriptionReference>
  <wsnt:CurrentTime>%s</wsnt:CurrentTime>
  <wsnt:TerminationTime>%s</wsnt:TerminationTime>
</tev:CreatePullPointSubscriptionResponse>`,
		d.ServiceURL("/onvif/subscription/"+subID),
		now.Format(time.RFC3339),
		term.Format(time.RFC3339)))

	log.Printf("Created subscription %s for %s", subID[:8], d.Name())
}

func (d *VirtualDevice) pullMessages(w http.ResponseWriter, body []byte, subID string) {
	d.mu.Lock()
	sub, ok := d.subscriptions[subID]
	d.mu.Unlock()

	if !ok {
		soap.WriteFault(w, "sender", "InvalidSubscription", "Subscription not found", 400)
		return
	}

	// Collect events with timeout
	var events []string
	timeout := 10 * time.Second
	timer := time.NewTimer(timeout)
	defer timer.Stop()

	// Drain available events first
loop:
	for {
		select {
		case evt := <-sub.Events:
			events = append(events, evt)
			if len(events) >= 100 {
				break loop
			}
		default:
			break loop
		}
	}

	// If no events, wait for one
	if len(events) == 0 {
		select {
		case evt := <-sub.Events:
			events = append(events, evt)
		case <-timer.C:
		}
	}

	now := time.Now().UTC()
	term := now.Add(60 * time.Second)
	eventsXML := strings.Join(events, "\n")

	soap.WriteSOAP(w, fmt.Sprintf(`
<tev:PullMessagesResponse xmlns:tev="http://www.onvif.org/ver10/events/wsdl" xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <tev:CurrentTime>%s</tev:CurrentTime>
  <tev:TerminationTime>%s</tev:TerminationTime>
  %s
</tev:PullMessagesResponse>`, now.Format(time.RFC3339), term.Format(time.RFC3339), eventsXML))
}

func (d *VirtualDevice) renew(w http.ResponseWriter, subID string) {
	d.mu.Lock()
	sub, ok := d.subscriptions[subID]
	if ok {
		sub.Created = time.Now()
	}
	d.mu.Unlock()

	now := time.Now().UTC()
	term := now.Add(60 * time.Second)
	soap.WriteSOAP(w, fmt.Sprintf(`
<wsnt:RenewResponse xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2">
  <wsnt:TerminationTime>%s</wsnt:TerminationTime>
  <wsnt:CurrentTime>%s</wsnt:CurrentTime>
</wsnt:RenewResponse>`, term.Format(time.RFC3339), now.Format(time.RFC3339)))
}

func (d *VirtualDevice) unsubscribe(w http.ResponseWriter, subID string) {
	d.mu.Lock()
	delete(d.subscriptions, subID)
	d.mu.Unlock()
	soap.WriteSOAP(w, `<wsnt:UnsubscribeResponse xmlns:wsnt="http://docs.oasis-open.org/wsn/b-2"/>`)
}

