// orcheck verifies the OpenRouter key Pink Diamond is configured with.
//
// It answers the update spec's question — "is the OpenRouter console key
// connected?" — without ever printing the key:
//
//	OPENROUTER_API_KEY=sk-or-... go run .
//	go run . -site https://pink-diamond-eight.vercel.app   # ask the deployment
//
// A management (provisioning) key authenticates against /api/v1/key but is
// refused by /chat/completions, so it is reported as connected-but-unusable.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"
)

const defaultAPI = "https://openrouter.ai/api/v1"

// KeyInfo is the subset of GET /api/v1/key that matters here.
type KeyInfo struct {
	Label          string   `json:"label"`
	IsManagement   bool     `json:"is_management_key"`
	IsProvisioning bool     `json:"is_provisioning_key"`
	Limit          *float64 `json:"limit"`
	LimitRemaining *float64 `json:"limit_remaining"`
	Usage          float64  `json:"usage"`
	IsFreeTier     bool     `json:"is_free_tier"`
}

// Verdict is what Pink Diamond needs to know about a key.
type Verdict struct {
	Configured     bool   `json:"configured"`
	InferenceReady bool   `json:"inference_ready"`
	KeyType        string `json:"key_type,omitempty"`
	Label          string `json:"label,omitempty"`
	Detail         string `json:"detail"`
}

// Classify turns the key-info response into a verdict.
func Classify(status int, info *KeyInfo) Verdict {
	switch {
	case status == http.StatusUnauthorized || status == http.StatusForbidden:
		return Verdict{Configured: true, Detail: fmt.Sprintf("key rejected by OpenRouter (%d)", status)}
	case status != http.StatusOK || info == nil:
		return Verdict{Configured: true, Detail: fmt.Sprintf("unexpected OpenRouter response (%d)", status)}
	case info.IsManagement || info.IsProvisioning:
		return Verdict{Configured: true, KeyType: "management", Label: info.Label,
			Detail: "management keys cannot call chat completions; create an inference key and set OPENROUTER_API_KEY to it"}
	case info.LimitRemaining != nil && *info.LimitRemaining <= 0:
		return Verdict{Configured: true, KeyType: "inference", Label: info.Label,
			Detail: "inference key has no credit limit remaining"}
	default:
		return Verdict{Configured: true, InferenceReady: true, KeyType: "inference", Label: info.Label, Detail: "connected"}
	}
}

// CheckKey asks OpenRouter about `key`.
func CheckKey(client *http.Client, api, key string) Verdict {
	if strings.TrimSpace(key) == "" {
		return Verdict{Detail: "OPENROUTER_API_KEY is not set"}
	}
	req, err := http.NewRequest(http.MethodGet, strings.TrimRight(api, "/")+"/key", nil)
	if err != nil {
		return Verdict{Configured: true, Detail: err.Error()}
	}
	req.Header.Set("Authorization", "Bearer "+key)
	resp, err := client.Do(req)
	if err != nil {
		return Verdict{Configured: true, Detail: "OpenRouter unreachable: " + err.Error()}
	}
	defer resp.Body.Close()
	var body struct {
		Data *KeyInfo `json:"data"`
	}
	if resp.StatusCode == http.StatusOK {
		if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
			return Verdict{Configured: true, Detail: "unreadable OpenRouter response"}
		}
	}
	return Classify(resp.StatusCode, body.Data)
}

// CheckSite asks a Pink Diamond deployment's /api/openrouter/status.
func CheckSite(client *http.Client, site string) (Verdict, error) {
	resp, err := client.Get(strings.TrimRight(site, "/") + "/api/openrouter/status")
	if err != nil {
		return Verdict{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return Verdict{}, fmt.Errorf("status endpoint returned %d", resp.StatusCode)
	}
	var v Verdict
	return v, json.NewDecoder(resp.Body).Decode(&v)
}

func main() {
	site := flag.String("site", "", "check a deployed Pink Diamond instead of the local env key")
	api := flag.String("api", defaultAPI, "OpenRouter API base")
	flag.Parse()

	client := &http.Client{Timeout: 15 * time.Second}
	var v Verdict
	if *site != "" {
		var err error
		if v, err = CheckSite(client, *site); err != nil {
			fmt.Fprintln(os.Stderr, "orcheck:", err)
			os.Exit(2)
		}
	} else {
		v = CheckKey(client, *api, os.Getenv("OPENROUTER_API_KEY"))
	}
	out, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(out))
	if !v.InferenceReady {
		os.Exit(1)
	}
}
