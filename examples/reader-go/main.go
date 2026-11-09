// Minimal language-neutral contract reader. AGPL-3.0-or-later.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

type Dependency struct {
	AssetID  string `json:"assetId"`
	Required bool   `json:"required"`
}
type Asset struct {
	AssetID      string       `json:"assetId"`
	Dependencies []Dependency `json:"dependencies"`
}
type Representation struct {
	SHA string `json:"sha256"`
}
type Version struct {
	AssetID         string           `json:"assetId"`
	Availability    string           `json:"availability"`
	Representations []Representation `json:"representations"`
}
type Story struct {
	ScriptID string `json:"scriptId"`
}
type Bundle struct {
	Snapshot struct {
		ID     string `json:"snapshotId"`
		Schema string `json:"schemaVersion"`
	} `json:"snapshot"`
	Assets   []Asset   `json:"assets"`
	Versions []Version `json:"versions"`
	Stories  []Story   `json:"stories"`
}

func run() error {
	if len(os.Args) != 2 {
		return fmt.Errorf("expected bundle path")
	}
	raw, err := os.ReadFile(os.Args[1])
	if err != nil {
		return err
	}
	var b Bundle
	if err = json.Unmarshal(raw, &b); err != nil {
		return err
	}
	if b.Snapshot.Schema != "1.0.0" {
		return fmt.Errorf("unsupported schema")
	}
	ids := map[string]bool{}
	states := map[string]string{}
	assets := []string{}
	stories := []string{}
	representations := []string{}
	dependencies := []string{}
	for _, a := range b.Assets {
		if ids[a.AssetID] {
			return fmt.Errorf("duplicate asset")
		}
		ids[a.AssetID] = true
		assets = append(assets, a.AssetID)
	}
	for _, v := range b.Versions {
		if !ids[v.AssetID] || states[v.AssetID] != "" {
			return fmt.Errorf("invalid version")
		}
		states[v.AssetID] = v.Availability
		for _, r := range v.Representations {
			representations = append(representations, r.SHA)
		}
	}
	if len(ids) != len(states) {
		return fmt.Errorf("missing version")
	}
	for _, a := range b.Assets {
		for _, d := range a.Dependencies {
			if !ids[d.AssetID] {
				return fmt.Errorf("missing dependency")
			}
			if d.Required && states[a.AssetID] == "available" && states[d.AssetID] != "available" {
				return fmt.Errorf("required dependency unavailable")
			}
			dependencies = append(dependencies, fmt.Sprintf("%s|%s|%t", a.AssetID, d.AssetID, d.Required))
		}
	}
	for _, s := range b.Stories {
		stories = append(stories, s.ScriptID)
	}
	sort.Strings(assets)
	sort.Strings(stories)
	sort.Strings(representations)
	sort.Strings(dependencies)
	return json.NewEncoder(os.Stdout).Encode(map[string]any{"snapshotId": b.Snapshot.ID, "assets": assets, "stories": stories, "representations": representations, "dependencies": dependencies})
}
func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
