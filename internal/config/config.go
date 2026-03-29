package config

import (
	"crypto/sha1"
	"fmt"
	"os"

	"github.com/google/uuid"
	"gopkg.in/yaml.v3"
)

type NVRConfig struct {
	Host     string `yaml:"host"`
	Port     int    `yaml:"port"`
	RTSPPort int    `yaml:"rtsp_port"`
	Username string `yaml:"username"`
	Password string `yaml:"password"`
}

type ChannelConfig struct {
	Channel    int    `yaml:"channel"`
	IP         string `yaml:"ip"`
	Name       string `yaml:"name"`
	MAC        string `yaml:"mac"`
	Port       int    `yaml:"port"`
	DeviceUUID string `yaml:"device_uuid"`
}

type Config struct {
	NVR       NVRConfig       `yaml:"nvr"`
	Channels  []ChannelConfig `yaml:"channels"`
	ONVIFPort int             `yaml:"onvif_port"`
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	cfg := &Config{
		NVR: NVRConfig{
			Port:     80,
			RTSPPort: 554,
			Username: "admin",
		},
		ONVIFPort: 8080,
	}

	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	// Fill defaults
	for i := range cfg.Channels {
		ch := &cfg.Channels[i]
		if ch.Name == "" {
			ch.Name = fmt.Sprintf("Camera %d", ch.Channel)
		}
		if ch.Port == 0 {
			ch.Port = cfg.ONVIFPort
		}
		if ch.DeviceUUID == "" {
			h := sha1.Sum([]byte(fmt.Sprintf("onvif-splitter-ch%d", ch.Channel)))
			ch.DeviceUUID = uuid.NewSHA1(uuid.Nil, h[:]).String()
		}
	}

	return cfg, nil
}
