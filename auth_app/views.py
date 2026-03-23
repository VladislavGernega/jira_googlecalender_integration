import json
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse, HttpRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from google_auth_oauthlib.flow import Flow

from sync.models import JiraUser

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_oauth_flow(request: HttpRequest) -> Flow:
    """Create OAuth flow with Google credentials."""
    client_config = {
        'web': {
            'client_id': settings.GOOGLE_CLIENT_ID,
            'client_secret': settings.GOOGLE_CLIENT_SECRET,
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [settings.GOOGLE_REDIRECT_URI],
        }
    }

    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = settings.GOOGLE_REDIRECT_URI
    return flow

def google_oauth_start(request: HttpRequest) -> HttpResponse:
    """Start Google OAuth flow."""
    flow = get_oauth_flow(request)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    request.session['oauth_state'] = state
    return redirect(authorization_url)

def google_oauth_callback(request: HttpRequest) -> HttpResponse:
    """Handle Google OAuth callback."""
    state = request.session.get('oauth_state')

    if not state:
        return HttpResponse("Missing OAuth state", status=400)

    flow = get_oauth_flow(request)
    flow.fetch_token(authorization_response=request.build_absolute_uri())

    credentials = flow.credentials
    credentials_dict = {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
    }

    # Store in session for linking step
    request.session['google_credentials'] = json.dumps(credentials_dict)

    return HttpResponse(
        """
        <html>
        <body>
            <h1>Google Calendar Connected!</h1>
            <p>Enter your Jira email to link your account:</p>
            <form method="POST" action="/auth/google/link/">
                <input type="email" name="email" placeholder="your-jira@email.com" required>
                <button type="submit">Link Account</button>
            </form>
        </body>
        </html>
        """,
        content_type='text/html'
    )

@csrf_exempt
@require_POST
def google_oauth_link(request: HttpRequest) -> HttpResponse:
    """Link Google credentials to Jira user by email."""
    email = request.POST.get('email', '').strip()
    credentials_json = request.session.get('google_credentials')

    if not email:
        return HttpResponse("Email required", status=400)

    if not credentials_json:
        return HttpResponse("No Google credentials in session. Please start OAuth flow again.", status=400)

    try:
        user = JiraUser.objects.get(email=email)
    except JiraUser.DoesNotExist:
        # Create new user record
        user = JiraUser.objects.create(
            email=email,
            jira_account_id='',  # Will be populated on first sync
            display_name=email.split('@')[0],
            google_calendar_id='primary'
        )

    user.set_google_credentials(credentials_json)
    user.is_active = True
    user.save()

    # Clear session
    del request.session['google_credentials']

    return HttpResponse(
        f"""
        <html>
        <body>
            <h1>Account Linked!</h1>
            <p>Your Google Calendar is now connected for {email}.</p>
            <p>Sync will begin within 30 seconds.</p>
        </body>
        </html>
        """,
        content_type='text/html'
    )
