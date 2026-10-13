package cli

import "testing"

func TestParseProgramArg(t *testing.T) {
	r, err := parseProgramArg("352")
	if err != nil || r.ID != 352 || r.UnitID != 0 {
		t.Fatal(r, err)
	}
	r, err = parseProgramArg("https://obs.mersin.edu.tr/oibs/bologna/index.aspx?lang=tr&curOp=showPac&curUnit=12&curSunit=352#")
	if err != nil || r.ID != 352 || r.UnitID != 12 {
		t.Fatal(r, err)
	}
	if _, err := parseProgramArg("abc"); err == nil {
		t.Fatal("hata bekleniyordu")
	}
}

func TestLevelList(t *testing.T) {
	if _, err := levelList([]string{"lisans", "yanlis"}, false); err == nil {
		t.Fatal("bilinmeyen seviye kabul edildi")
	}
	if l, _ := levelList(nil, true); len(l) != 4 {
		t.Fatal(l)
	}
}

func TestParseYears(t *testing.T) {
	for in, want := range map[string]int{"1": 1, "3": 3, "all": -1, "ALL": -1} {
		if got, err := parseYears(in); err != nil || got != want {
			t.Fatalf("%q -> %d, %v", in, got, err)
		}
	}
	for _, bad := range []string{"0", "-2", "x", ""} {
		if _, err := parseYears(bad); err == nil {
			t.Fatalf("%q kabul edildi", bad)
		}
	}
}

func TestNormalizeBaseURL(t *testing.T) {
	for in, want := range map[string]string{
		"https://obs.mersin.edu.tr/oibs/bologna/": "https://obs.mersin.edu.tr/oibs/bologna/",
		"obs.cu.edu.tr":                      "https://obs.cu.edu.tr/oibs/bologna/",
		"https://obs.cu.edu.tr":              "https://obs.cu.edu.tr/oibs/bologna/",
		"http://127.0.0.1:8080/oibs/bologna": "http://127.0.0.1:8080/oibs/bologna/",
		"https://obs.cu.edu.tr/oibs/bologna/index.aspx?lang=tr&curOp=showPac&curSunit=5": "https://obs.cu.edu.tr/oibs/bologna/",
		"https://ornek.edu.tr/bilgipaketi/index.aspx":                                    "https://ornek.edu.tr/bilgipaketi/",
	} {
		if got, err := normalizeBaseURL(in); err != nil || got != want {
			t.Errorf("%q -> %q, %v (beklenen %q)", in, got, err, want)
		}
	}
	if _, err := normalizeBaseURL(" "); err == nil {
		t.Error("boş adres kabul edildi")
	}
}

func TestSchemaFor(t *testing.T) {
	for in, want := range map[string]string{
		"https://obs.mersin.edu.tr/oibs/bologna/":    "public",
		"https://obs.cu.edu.tr/oibs/bologna/":        "cu",
		"https://obs.selcuk.edu.tr/oibs/bologna/":    "selcuk",
		"https://ebs.ornek-uni.edu.tr/oibs/bologna/": "ebs_ornek_uni",
		"http://127.0.0.1:8080/oibs/bologna/":        "s_127_0_0_1",
	} {
		if got, err := schemaFor(in, ""); err != nil || got != want {
			t.Errorf("%q -> %q, %v (beklenen %q)", in, got, err, want)
		}
	}
	if got, _ := schemaFor("https://obs.cu.edu.tr/oibs/bologna/", "Cukurova"); got != "cukurova" {
		t.Error(got)
	}
	if _, err := schemaFor("https://obs.cu.edu.tr/", "drop table;"); err == nil {
		t.Error("geçersiz şema kabul edildi")
	}
}
