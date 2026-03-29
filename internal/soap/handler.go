package soap

import (
	"crypto/sha1"
	"encoding/base64"
	"encoding/xml"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"strings"
	"time"
)

// Envelope is a minimal SOAP envelope parser
type Envelope struct {
	XMLName xml.Name `xml:"Envelope"`
	Header  Header   `xml:"Header"`
	Body    Body     `xml:"Body"`
}

type Header struct {
	Security *Security `xml:",any"`
}

type Security struct {
	UsernameToken *UsernameToken `xml:",any"`
}

type UsernameToken struct {
	Username string `xml:"Username"`
	Password struct {
		Value string `xml:",chardata"`
		Type  string `xml:"Type,attr"`
	} `xml:"Password"`
	Nonce struct {
		Value string `xml:",chardata"`
	} `xml:"Nonce"`
	Created string `xml:"Created"`
}

type Body struct {
	Inner []byte `xml:",innerxml"`
}

func ParseAction(body []byte) string {
	// Find the first element inside Body
	d := xml.NewDecoder(strings.NewReader(string(body)))
	for {
		tok, err := d.Token()
		if err != nil {
			return ""
		}
		if se, ok := tok.(xml.StartElement); ok {
			return se.Name.Local
		}
	}
}

func ValidateAuth(env *Envelope, username, password string) bool {
	if env.Header.Security == nil || env.Header.Security.UsernameToken == nil {
		// Try finding it in raw XML
		return false
	}

	token := env.Header.Security.UsernameToken
	if token.Username != username {
		return false
	}

	ptype := token.Password.Type
	if strings.Contains(ptype, "PasswordDigest") {
		nonceBytes, err := base64.StdEncoding.DecodeString(token.Nonce.Value)
		if err != nil {
			return false
		}
		created := []byte(token.Created)
		h := sha1.New()
		h.Write(nonceBytes)
		h.Write(created)
		h.Write([]byte(password))
		expected := base64.StdEncoding.EncodeToString(h.Sum(nil))

		if token.Password.Value != expected {
			return false
		}

		// Check clock skew (5 min)
		t, err := time.Parse(time.RFC3339, strings.Replace(token.Created, "Z", "+00:00", 1))
		if err == nil {
			delta := math.Abs(time.Since(t).Seconds())
			if delta > 300 {
				log.Printf("Clock skew too large: %.0fs", delta)
				return false
			}
		}
	} else {
		// Plain text
		if token.Password.Value != password {
			return false
		}
	}
	return true
}

// ValidateAuthFlexible tries standard XML parsing first, falls back to string parsing
func ValidateAuthFlexible(body []byte, username, password string) bool {
	var env Envelope
	if err := xml.Unmarshal(body, &env); err == nil {
		if env.Header.Security != nil {
			return ValidateAuth(&env, username, password)
		}
	}

	// Fallback: parse Username/Password/Nonce/Created from raw XML
	s := string(body)

	extractTag := func(tag string) string {
		start := strings.Index(s, "<")
		for start >= 0 {
			end := strings.Index(s[start:], ">")
			if end < 0 {
				break
			}
			tagEnd := start + end + 1
			elem := s[start:tagEnd]
			if strings.Contains(elem, tag) && !strings.Contains(elem, "/") {
				valEnd := strings.Index(s[tagEnd:], "</")
				if valEnd >= 0 {
					return strings.TrimSpace(s[tagEnd : tagEnd+valEnd])
				}
			}
			start = strings.Index(s[tagEnd:], "<")
			if start >= 0 {
				start += tagEnd
			}
		}
		return ""
	}

	u := extractTag("Username")
	if u != username {
		return false
	}

	// Find Password element and its Type attribute
	pwIdx := strings.Index(s, "Password")
	if pwIdx < 0 {
		return false
	}
	pwSection := s[pwIdx:]
	pwEnd := strings.Index(pwSection, "</")
	if pwEnd < 0 {
		return false
	}
	pwTagEnd := strings.Index(pwSection, ">")
	if pwTagEnd < 0 {
		return false
	}
	pwValue := strings.TrimSpace(pwSection[pwTagEnd+1 : pwEnd])
	isDigest := strings.Contains(pwSection[:pwTagEnd], "PasswordDigest")

	if isDigest {
		nonce := extractTag("Nonce")
		created := extractTag("Created")
		nonceBytes, err := base64.StdEncoding.DecodeString(nonce)
		if err != nil {
			return false
		}
		h := sha1.New()
		h.Write(nonceBytes)
		h.Write([]byte(created))
		h.Write([]byte(password))
		expected := base64.StdEncoding.EncodeToString(h.Sum(nil))
		return pwValue == expected
	}

	return pwValue == password
}

func WriteSOAP(w http.ResponseWriter, body string) {
	w.Header().Set("Content-Type", "application/soap+xml; charset=utf-8")
	fmt.Fprintf(w, `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
<s:Body>%s</s:Body>
</s:Envelope>`, body)
}

func WriteFault(w http.ResponseWriter, code, subcode, reason string, status int) {
	w.Header().Set("Content-Type", "application/soap+xml; charset=utf-8")
	w.WriteHeader(status)
	fmt.Fprintf(w, `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">
<s:Body><s:Fault>
<s:Code><s:Value>s:%s</s:Value><s:Subcode><s:Value>%s</s:Value></s:Subcode></s:Code>
<s:Reason><s:Text xml:lang="en">%s</s:Text></s:Reason>
</s:Fault></s:Body></s:Envelope>`, code, subcode, reason)
}

func ReadBody(r *http.Request) ([]byte, error) {
	defer r.Body.Close()
	return io.ReadAll(r.Body)
}
