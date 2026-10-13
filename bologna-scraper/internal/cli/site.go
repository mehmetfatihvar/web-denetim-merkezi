package cli

import (
	"fmt"
	"net/url"
	"regexp"
	"strings"
)

// Varsayılan site: Mersin Üniversitesi. Verisi geriye uyum için "public" şemasında kalır.
const (
	defaultBaseURL = "https://obs.mersin.edu.tr/oibs/bologna/"
	defaultHost    = "obs.mersin.edu.tr"
	bolognaPath    = "/oibs/bologna/"
)

// normalizeBaseURL, kullanıcının verdiği adresi OİBS Bologna kök adresine çevirir.
// "obs.cu.edu.tr", "https://obs.cu.edu.tr" ve tarayıcıdan kopyalanan
// ".../oibs/bologna/index.aspx?..." biçimlerinin hepsi kabul edilir.
func normalizeBaseURL(s string) (string, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return "", fmt.Errorf("--base-url boş")
	}
	if !strings.Contains(s, "://") {
		s = "https://" + s
	}
	u, err := url.Parse(s)
	if err != nil || u.Host == "" {
		return "", fmt.Errorf("--base-url %q: geçerli bir adres değil", s)
	}
	p := u.Path
	if i := strings.Index(strings.ToLower(p), "/oibs/bologna"); i >= 0 {
		p = p[:i] + bolognaPath
	} else if strings.HasSuffix(strings.ToLower(p), ".aspx") {
		p = p[:strings.LastIndex(p, "/")+1]
	} else if p == "" || p == "/" {
		p = bolognaPath
	}
	if !strings.HasSuffix(p, "/") {
		p += "/"
	}
	return u.Scheme + "://" + u.Host + p, nil
}

func hostOf(base string) string {
	u, err := url.Parse(base)
	if err != nil {
		return ""
	}
	return strings.ToLower(u.Hostname())
}

var (
	reSchema     = regexp.MustCompile(`^[a-z_][a-z0-9_]{0,62}$`)
	reNonIdent   = regexp.MustCompile(`[^a-z0-9]+`)
	hostSuffixes = []string{".edu.tr", ".edu", ".ac.uk", ".com.tr", ".org.tr", ".gov.tr", ".com", ".org", ".net"}
)

// schemaFor, siteye ait verinin yazılacağı PostgreSQL şemasını seçer. Aynı veritabanında birden
// çok üniversite durabilsin diye her site kendi şemasına yazar (kimlikler siteler arasında çakışır).
// Mersin Üniversitesi önceki sürümlerle uyumlu kalmak için "public" kullanır.
func schemaFor(base, explicit string) (string, error) {
	if explicit != "" {
		s := strings.ToLower(explicit)
		if !reSchema.MatchString(s) {
			return "", fmt.Errorf("--schema %q: küçük harf, rakam ve _ olmalı (ör. cukurova)", explicit)
		}
		return s, nil
	}
	h := hostOf(base)
	if h == defaultHost || h == "" {
		return "public", nil
	}
	for _, p := range []string{"obs.", "oibs.", "www.", "bologna.", "ects."} {
		h = strings.TrimPrefix(h, p)
	}
	for _, s := range hostSuffixes {
		if strings.HasSuffix(h, s) {
			h = strings.TrimSuffix(h, s)
			break
		}
	}
	s := strings.Trim(reNonIdent.ReplaceAllString(h, "_"), "_")
	if s == "" || s == "public" {
		s = "site"
	}
	if s[0] >= '0' && s[0] <= '9' {
		s = "s_" + s
	}
	if len(s) > 63 {
		s = s[:63]
	}
	return s, nil
}
