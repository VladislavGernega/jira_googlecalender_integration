# sync/jira_client.py
import base64
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

class JiraClient:
    """Wrapper for Jira Cloud REST API."""

    def __init__(self, base_url: str, email: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.email = email
        self.api_token = api_token

    def _build_headers(self) -> Dict[str, str]:
        """Build authentication headers for Jira API."""
        credentials = f"{self.email}:{self.api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return {
            'Authorization': f'Basic {encoded}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

    def get_issues_updated_since(
        self,
        projects: List[str],
        issue_types: List[str],
        since_minutes: int = 5,
        additional_jql: str = ''
    ) -> List[Dict[str, Any]]:
        """Fetch issues updated since given time with due dates."""
        project_jql = f"project IN ({','.join(projects)})"
        type_jql = f"issuetype IN ({','.join(issue_types)})"
        time_jql = f"updated >= -{since_minutes}m"
        due_jql = "duedate IS NOT EMPTY"

        jql_parts = [project_jql, type_jql, time_jql, due_jql]
        if additional_jql:
            jql_parts.append(f"({additional_jql})")

        jql = " AND ".join(jql_parts)

        url = f"{self.base_url}/rest/api/3/search"
        params = {
            'jql': jql,
            'fields': 'summary,duedate,assignee,status,priority,labels,description,updated'
        }

        response = requests.get(url, headers=self._build_headers(), params=params)
        response.raise_for_status()
        return response.json().get('issues', [])

    def get_issue(self, issue_key: str) -> Dict[str, Any]:
        """Fetch a single issue by key."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        params = {
            'fields': 'summary,duedate,assignee,status,priority,labels,description,updated'
        }

        response = requests.get(url, headers=self._build_headers(), params=params)
        response.raise_for_status()
        return response.json()

    def update_issue(self, issue_key: str, fields: Dict[str, Any]) -> None:
        """Update issue fields."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        data = {'fields': fields}

        response = requests.put(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def add_comment(self, issue_key: str, body: str) -> None:
        """Add a comment to an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}/comment"
        data = {
            'body': {
                'type': 'doc',
                'version': 1,
                'content': [
                    {
                        'type': 'paragraph',
                        'content': [{'type': 'text', 'text': body}]
                    }
                ]
            }
        }

        response = requests.post(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def add_label(self, issue_key: str, label: str) -> None:
        """Add a label to an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        data = {
            'update': {
                'labels': [{'add': label}]
            }
        }

        response = requests.put(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def remove_label(self, issue_key: str, label: str) -> None:
        """Remove a label from an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"
        data = {
            'update': {
                'labels': [{'remove': label}]
            }
        }

        response = requests.put(url, headers=self._build_headers(), json=data)
        response.raise_for_status()

    def delete_issue(self, issue_key: str) -> None:
        """Delete an issue."""
        url = f"{self.base_url}/rest/api/3/issue/{issue_key}"

        response = requests.delete(url, headers=self._build_headers())
        response.raise_for_status()
