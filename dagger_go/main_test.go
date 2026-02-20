package main

import (
	"fmt"
	"os"
	"runtime"
	"testing"
)

// TestRepositoryConfiguration tests repository configuration
func TestRepositoryConfiguration(t *testing.T) {
	pipeline := &Pipeline{
		RepoName:            "cert-parser",
		GitRepo:             "https://github.com/test/cert-parser.git",
		GitBranch:           "main",
		GitUser:             "testuser",
		RunUnitTests:        true,
		RunIntegrationTests: true,
		RunAcceptanceTests:  true,
		RunLint:             true,
		RunTypeCheck:        true,
	}

	if pipeline.RepoName == "" {
		t.Fatal("RepoName is empty")
	}
	if pipeline.GitRepo == "" {
		t.Fatal("GitRepo is empty")
	}
	if pipeline.GitBranch == "" {
		t.Fatal("GitBranch is empty")
	}

	fmt.Printf("✅ Repository config valid: %s (%s)\n", pipeline.RepoName, pipeline.GitBranch)
}

// TestPipelineDefaultFlags tests that Pipeline flags default to zero values
func TestPipelineDefaultFlags(t *testing.T) {
	pipeline := &Pipeline{}

	// Go zero values — bool defaults to false
	if pipeline.RunUnitTests {
		t.Fatal("RunUnitTests should default to false (zero value)")
	}
	if pipeline.RunIntegrationTests {
		t.Fatal("RunIntegrationTests should default to false (zero value)")
	}
	if pipeline.RunAcceptanceTests {
		t.Fatal("RunAcceptanceTests should default to false (zero value)")
	}
	if pipeline.HasDocker {
		t.Fatal("HasDocker should default to false (zero value)")
	}

	fmt.Println("✅ Pipeline flags correctly default to zero values")
}

// TestPipelineConfigurableFlags tests explicit flag configuration
func TestPipelineConfigurableFlags(t *testing.T) {
	pipeline := &Pipeline{
		RepoName:            "cert-parser",
		RunUnitTests:        true,
		RunIntegrationTests: false,
		RunAcceptanceTests:  true,
		RunLint:             true,
		RunTypeCheck:        false,
		HasDocker:           true,
	}

	if !pipeline.RunUnitTests {
		t.Fatal("RunUnitTests should be true")
	}
	if pipeline.RunIntegrationTests {
		t.Fatal("RunIntegrationTests should be false")
	}
	if !pipeline.RunAcceptanceTests {
		t.Fatal("RunAcceptanceTests should be true")
	}
	if !pipeline.HasDocker {
		t.Fatal("HasDocker should be true")
	}
	if pipeline.RunTypeCheck {
		t.Fatal("RunTypeCheck should be false")
	}

	fmt.Println("✅ Pipeline configurable flags work correctly")
}

// TestEnvironmentVariables tests required environment variables
func TestEnvironmentVariables(t *testing.T) {
	requiredVars := []string{"CR_PAT", "USERNAME"}

	for _, varName := range requiredVars {
		if _, exists := os.LookupEnv(varName); !exists {
			fmt.Printf("⚠️  %s not set (required for full pipeline)\n", varName)
		}
	}

	fmt.Println("✅ Environment variable checks completed")
}

// TestImageNaming tests Docker image naming logic
func TestImageNaming(t *testing.T) {
	pipeline := &Pipeline{
		ImageName: "cert-parser",
		GitUser:   "javier-godon",
	}

	imageName := fmt.Sprintf("ghcr.io/%s/%s:v0.1.0", pipeline.GitUser, pipeline.ImageName)

	if imageName == "" {
		t.Fatal("Image name is empty")
	}
	if !contains(imageName, "ghcr.io") {
		t.Fatal("Image name should contain registry")
	}

	fmt.Printf("✅ Image naming valid: %s\n", imageName)
}

// TestGitRepositoryURL tests Git repository URL construction
func TestGitRepositoryURL(t *testing.T) {
	username := "testuser"
	repoName := "cert-parser"

	gitRepo := fmt.Sprintf("https://github.com/%s/%s.git", username, repoName)

	if !contains(gitRepo, "github.com") {
		t.Fatal("Git repository URL should contain github.com")
	}
	if !contains(gitRepo, repoName) {
		t.Fatal("Git repository URL should contain repository name")
	}

	fmt.Printf("✅ Git repository URL valid: %s\n", gitRepo)
}

// TestExtractProjectName tests pyproject.toml name extraction
func TestExtractProjectName(t *testing.T) {
	content := `[project]
name = "cert-parser"
version = "0.1.0"
description = "ICAO Master List certificate parser"
`
	name := extractProjectName(content)
	if name != "cert-parser" {
		t.Fatalf("Expected 'cert-parser', got '%s'", name)
	}
	fmt.Printf("✅ Extracted project name: %s\n", name)
}

// TestExtractProjectNameMissing tests fallback when name is absent
func TestExtractProjectNameMissing(t *testing.T) {
	content := `[project]
version = "0.1.0"
`
	name := extractProjectName(content)
	if name != "" {
		t.Fatalf("Expected empty string, got '%s'", name)
	}
	fmt.Println("✅ Empty name correctly returned for missing field")
}

// TestDockerSafeName tests Docker-safe naming
func TestDockerSafeName(t *testing.T) {
	tests := []struct {
		input    string
		expected string
	}{
		{"cert-parser", "cert-parser"},
		{"cert_parser", "cert-parser"},
		{"My_Project", "my-project"},
	}
	for _, tc := range tests {
		result := dockerSafeName(tc.input)
		if result != tc.expected {
			t.Fatalf("dockerSafeName(%q) = %q, want %q", tc.input, result, tc.expected)
		}
	}
	fmt.Println("✅ Docker-safe naming works correctly")
}

// TestParseEnvBoolDefaults tests parseEnvBool with unset variables
func TestParseEnvBoolDefaults(t *testing.T) {
	// Ensure the env var is NOT set
	os.Unsetenv("TEST_PARSE_BOOL_UNSET")

	if !parseEnvBool("TEST_PARSE_BOOL_UNSET", true) {
		t.Fatal("Expected true when env var is unset and default is true")
	}
	if parseEnvBool("TEST_PARSE_BOOL_UNSET", false) {
		t.Fatal("Expected false when env var is unset and default is false")
	}

	fmt.Println("✅ parseEnvBool defaults work correctly")
}

// TestParseEnvBoolValues tests parseEnvBool with various values
func TestParseEnvBoolValues(t *testing.T) {
	tests := []struct {
		value    string
		expected bool
	}{
		{"true", true},
		{"True", true},
		{"TRUE", true},
		{"1", true},
		{"yes", true},
		{"Yes", true},
		{"YES", true},
		{"false", false},
		{"False", false},
		{"0", false},
		{"no", false},
		{"random", false},
	}

	for _, tc := range tests {
		os.Setenv("TEST_PARSE_BOOL", tc.value)
		result := parseEnvBool("TEST_PARSE_BOOL", false)
		if result != tc.expected {
			t.Fatalf("parseEnvBool(%q) = %v, want %v", tc.value, result, tc.expected)
		}
	}
	os.Unsetenv("TEST_PARSE_BOOL")

	fmt.Println("✅ parseEnvBool correctly parses all value variants")
}

// TestGetDockerSocketPath tests Docker socket detection
func TestGetDockerSocketPath(t *testing.T) {
	socketPath := getDockerSocketPath()

	if runtime.GOOS == "linux" || runtime.GOOS == "darwin" {
		// On CI or dev machines, Docker is usually available
		if socketPath != "" {
			fmt.Printf("✅ Docker socket found: %s\n", socketPath)
		} else {
			fmt.Println("⚠️  Docker socket not found (OK for environments without Docker)")
		}
	} else {
		fmt.Printf("⚠️  Docker socket detection on %s — result: %q\n", runtime.GOOS, socketPath)
	}
}

// Helper function to check if string contains substring
func contains(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
