package main

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

func fakeOpenRouter(t *testing.T, status int, body string) *httptest.Server {
	t.Helper()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/key" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer sk-or-test" {
			t.Errorf("missing bearer key")
		}
		w.WriteHeader(status)
		w.Write([]byte(body))
	}))
	t.Cleanup(srv.Close)
	return srv
}

func TestMissingKey(t *testing.T) {
	v := CheckKey(http.DefaultClient, "http://unused", "")
	if v.Configured || v.InferenceReady {
		t.Fatalf("empty key must be unconfigured: %+v", v)
	}
}

func TestManagementKeyIsNotInferenceReady(t *testing.T) {
	srv := fakeOpenRouter(t, 200, `{"data":{"label":"sk-or-v1-650...43e","is_management_key":true,"is_provisioning_key":true}}`)
	v := CheckKey(srv.Client(), srv.URL, "sk-or-test")
	if !v.Configured || v.InferenceReady || v.KeyType != "management" {
		t.Fatalf("management key misclassified: %+v", v)
	}
}

func TestInferenceKeyIsReady(t *testing.T) {
	srv := fakeOpenRouter(t, 200, `{"data":{"label":"sk-or-v1-abc...123","is_management_key":false,"limit_remaining":4.5}}`)
	v := CheckKey(srv.Client(), srv.URL, "sk-or-test")
	if !v.InferenceReady || v.KeyType != "inference" {
		t.Fatalf("inference key misclassified: %+v", v)
	}
}

func TestExhaustedKey(t *testing.T) {
	srv := fakeOpenRouter(t, 200, `{"data":{"label":"x","limit_remaining":0}}`)
	if v := CheckKey(srv.Client(), srv.URL, "sk-or-test"); v.InferenceReady {
		t.Fatalf("exhausted key reported ready: %+v", v)
	}
}

func TestRejectedKey(t *testing.T) {
	srv := fakeOpenRouter(t, 401, `{"error":{"message":"User not found.","code":401}}`)
	if v := CheckKey(srv.Client(), srv.URL, "sk-or-test"); v.InferenceReady || !v.Configured {
		t.Fatalf("rejected key misclassified: %+v", v)
	}
}

func TestCheckSite(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/openrouter/status" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		w.Write([]byte(`{"configured":false,"inference_ready":false,"detail":"OPENROUTER_API_KEY is not set in this environment"}`))
	}))
	defer srv.Close()
	v, err := CheckSite(srv.Client(), srv.URL)
	if err != nil || v.Configured {
		t.Fatalf("site check: %+v %v", v, err)
	}
}
