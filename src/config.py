"""
Configuration file for Sentry-Jira Agent
Phase 1: Setup & Authentication
"""

from dataclasses import dataclass
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class AtlassianConfig:
    """Atlassian/Jira configuration"""
    cloud_id: str = "53c4a0e6-1418-4427-8db5-d27cfe9b1751"
    jira_url: str = "https://remarkgroup.atlassian.net"
    jira_project: str = "MAFB"
    jira_sample_project: str = "SI"  # For testing
    
    def __post_init__(self):
        # Override from environment if available
        if env_cloud_id := os.getenv("ATLASSIAN_CLOUD_ID"):
            self.cloud_id = env_cloud_id
        if env_jira_url := os.getenv("ATLASSIAN_JIRA_URL"):
            self.jira_url = env_jira_url
        if env_jira_project := os.getenv("JIRA_PROJECT"):
            self.jira_project = env_jira_project


@dataclass
class SentryConfig:
    """Sentry configuration"""
    org_slug: str = "scor-digital-solutions"
    auth_token: Optional[str] = None  # Retrieved from environment
    user_id: str = "3672583"
    user_email: str = "jaedon.tan@scordigitalsolutions.com"
    
    def __post_init__(self):
        # Get token from environment
        if token := os.getenv("SENTRY_AUTH_TOKEN"):
            self.auth_token = token


@dataclass
class GitHubConfig:
    """GitHub configuration"""
    repo: str = "maf-hackathon-2025"
    owner: str = "SDS"  # Or organization name
    auth_token: Optional[str] = None
    
    def __post_init__(self):
        if token := os.getenv("GITHUB_TOKEN"):
            self.auth_token = token


@dataclass
class AzureConfig:
    """Azure VM deployment configuration"""
    host: str = "20.255.50.129"
    user: str = "mafb"
    ssh_port: int = 22
    api_port: int = 8000
    api_base_url: str = "http://20.255.50.129:8000"
    webhook_endpoint: str = "/webhook/sentry-issue"
    
    @property
    def full_endpoint_url(self) -> str:
        """Get full webhook endpoint URL"""
        return f"{self.api_base_url}{self.webhook_endpoint}"


@dataclass
class AppConfig:
    """Main application configuration"""
    atlassian: AtlassianConfig
    sentry: SentryConfig
    github: GitHubConfig
    azure: AzureConfig
    
    debug: bool = False
    
    def __post_init__(self):
        if env_debug := os.getenv("DEBUG"):
            self.debug = env_debug.lower() == "true"


# Global config instance
config = AppConfig(
    atlassian=AtlassianConfig(),
    sentry=SentryConfig(),
    github=GitHubConfig(),
    azure=AzureConfig(),
)


# For testing Phase 1 setup
if __name__ == "__main__":
    print("=== Sentry-Jira Agent Configuration ===\n")
    print("Atlassian Configuration:")
    print(f"  Cloud ID: {config.atlassian.cloud_id}")
    print(f"  Jira URL: {config.atlassian.jira_url}")
    print(f"  Target Project: {config.atlassian.jira_project}")
    
    print("\nSentry Configuration:")
    print(f"  Organization: {config.sentry.org_slug}")
    print(f"  User: {config.sentry.user_email}")
    print(f"  User ID: {config.sentry.user_id}")
    
    print("\nGitHub Configuration:")
    print(f"  Repository: {config.github.repo}")
    
    print("\nAzure Configuration:")
    print(f"  Host: {config.azure.host}")
    print(f"  API Base URL: {config.azure.api_base_url}")
    print(f"  Webhook Endpoint: {config.azure.webhook_endpoint}")
    print(f"  Full URL: {config.azure.full_endpoint_url}")
