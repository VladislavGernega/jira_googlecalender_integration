# sync/views.py
from datetime import datetime
from django.shortcuts import render
from django.conf import settings
from .jira_client import JiraClient
import requests


def get_jira_client() -> JiraClient:
    """Create Jira client from settings."""
    return JiraClient(
        base_url=settings.JIRA_BASE_URL,
        email=settings.JIRA_EMAIL,
        api_token=settings.JIRA_API_TOKEN
    )


def get_project_users(jira_client, project):
    """Fetch all users who have been assigned issues in the project."""
    url = f"{jira_client.base_url}/rest/api/3/user/assignable/search"
    params = {'project': project, 'maxResults': 100}
    try:
        response = requests.get(url, headers=jira_client._build_headers(), params=params)
        response.raise_for_status()
        users = response.json()
        return [{'id': u.get('accountId'), 'name': u.get('displayName')} for u in users]
    except:
        return []


def get_project_statuses(jira_client, project):
    """Fetch all statuses available in the project."""
    url = f"{jira_client.base_url}/rest/api/3/project/{project}/statuses"
    try:
        response = requests.get(url, headers=jira_client._build_headers())
        response.raise_for_status()
        data = response.json()
        statuses = set()
        for issue_type in data:
            for status in issue_type.get('statuses', []):
                statuses.add(status.get('name'))
        return sorted(list(statuses))
    except:
        return ['To Do', 'In Progress', 'Done']


def task_report(request):
    """Display report of tasks with filters for status and assignee."""
    jira_client = get_jira_client()

    # Get filter parameters
    project = request.GET.get('project', 'TT')
    assignee = request.GET.get('assignee', '')
    status_filter = request.GET.get('status', '')
    days = int(request.GET.get('days', 30))

    # Get available users and statuses for dropdowns
    available_users = get_project_users(jira_client, project)
    available_statuses = get_project_statuses(jira_client, project)

    # Build JQL
    jql_parts = [f'project = {project}']

    # Status filter
    if status_filter:
        jql_parts.append(f'status = "{status_filter}"')
        if status_filter.lower() == 'done':
            jql_parts.append(f'resolved >= -{days}d')
        else:
            jql_parts.append(f'updated >= -{days}d')
    else:
        # All statuses - get recently updated
        jql_parts.append(f'updated >= -{days}d')

    if assignee:
        jql_parts.append(f'assignee = "{assignee}"')

    jql = ' AND '.join(jql_parts) + ' ORDER BY updated DESC'

    # Fetch from Jira
    url = f"{jira_client.base_url}/rest/api/3/search/jql"
    data = {
        'jql': jql,
        'fields': ['summary', 'duedate', 'assignee', 'status', 'issuetype', 'resolutiondate', 'priority', 'created']
    }

    try:
        import requests
        response = requests.post(url, headers=jira_client._build_headers(), json=data)
        response.raise_for_status()
        issues = response.json().get('issues', [])
    except Exception as e:
        issues = []
        error = str(e)
    else:
        error = None

    # Process issues for display
    report_data = []
    on_time_count = 0
    late_count = 0

    for issue in issues:
        fields = issue.get('fields', {})

        # Parse dates
        due_date_str = fields.get('duedate')
        resolution_date_str = fields.get('resolutiondate')

        due_date = None
        resolution_date = None
        is_on_time = None
        days_diff = None

        if due_date_str:
            due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()

        if resolution_date_str:
            # Resolution date includes time, parse just the date part
            resolution_date = datetime.fromisoformat(resolution_date_str.replace('Z', '+00:00')).date()

        if due_date and resolution_date:
            days_diff = (due_date - resolution_date).days
            is_on_time = resolution_date <= due_date
            if is_on_time:
                on_time_count += 1
            else:
                late_count += 1

        assignee_info = fields.get('assignee') or {}
        issue_type = fields.get('issuetype') or {}
        priority = fields.get('priority') or {}
        status_info = fields.get('status') or {}

        report_data.append({
            'key': issue.get('key'),
            'url': f"{jira_client.base_url}/browse/{issue.get('key')}",
            'summary': fields.get('summary', ''),
            'issue_type': issue_type.get('name', 'Unknown'),
            'assignee': assignee_info.get('displayName', 'Unassigned'),
            'priority': priority.get('name', ''),
            'status': status_info.get('name', ''),
            'due_date': due_date,
            'resolution_date': resolution_date,
            'is_on_time': is_on_time,
            'days_diff': days_diff,
        })

    # Calculate stats
    total = len(report_data)
    on_time_pct = round((on_time_count / total) * 100, 1) if total > 0 else 0

    # Count by status
    status_counts = {}
    for task in report_data:
        s = task['status']
        status_counts[s] = status_counts.get(s, 0) + 1

    context = {
        'report_data': report_data,
        'project': project,
        'assignee_filter': assignee,
        'status_filter': status_filter,
        'days': days,
        'total': total,
        'on_time_count': on_time_count,
        'late_count': late_count,
        'on_time_pct': on_time_pct,
        'status_counts': status_counts,
        'available_users': available_users,
        'available_statuses': available_statuses,
        'error': error,
        'jira_base_url': jira_client.base_url,
    }

    return render(request, 'sync/task_report.html', context)
