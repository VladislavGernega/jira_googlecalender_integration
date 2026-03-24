import json
import os
import secrets
import hashlib
import base64
import uuid
import requests
from urllib.parse import urlencode
from django.conf import settings
from django.shortcuts import redirect
from django.http import HttpResponse, HttpRequest
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

from sync.models import JiraUser

# Allow OAuth over HTTP for local development
if settings.DEBUG:
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/calendar']
AUTH_URI = 'https://accounts.google.com/o/oauth2/auth'
TOKEN_URI = 'https://oauth2.googleapis.com/token'


def generate_code_verifier():
    """Generate a random code verifier for PKCE."""
    return secrets.token_urlsafe(64)


def generate_code_challenge(verifier):
    """Generate code challenge from verifier using SHA256."""
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode()


def google_oauth_start(request: HttpRequest) -> HttpResponse:
    """Start Google OAuth flow with PKCE."""
    state = secrets.token_urlsafe(32)
    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    # Store state and verifier in session
    request.session['oauth_state'] = state
    request.session['code_verifier'] = code_verifier

    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'scope': ' '.join(SCOPES),
        'response_type': 'code',
        'state': state,
        'access_type': 'offline',
        'prompt': 'consent',
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }

    authorization_url = f"{AUTH_URI}?{urlencode(params)}"
    return redirect(authorization_url)


def google_oauth_callback(request: HttpRequest) -> HttpResponse:
    """Handle Google OAuth callback."""
    # Verify state
    state = request.GET.get('state')
    stored_state = request.session.get('oauth_state')
    code_verifier = request.session.get('code_verifier')

    if not state or state != stored_state:
        return HttpResponse("Invalid OAuth state. Please <a href='/auth/google/'>try again</a>.", status=400)

    if not code_verifier:
        return HttpResponse("Missing code verifier. Please <a href='/auth/google/'>try again</a>.", status=400)

    # Check for errors
    error = request.GET.get('error')
    if error:
        return HttpResponse(f"OAuth error: {error}", status=400)

    # Get authorization code
    code = request.GET.get('code')
    if not code:
        return HttpResponse("Missing authorization code.", status=400)

    # Exchange code for tokens (with PKCE verifier)
    token_data = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'code_verifier': code_verifier,
    }

    response = requests.post(TOKEN_URI, data=token_data)

    if response.status_code != 200:
        return HttpResponse(f"Token exchange failed: {response.text}<br><br><a href='/auth/google/'>Try again</a>", status=400)

    tokens = response.json()

    credentials_dict = {
        'token': tokens.get('access_token'),
        'refresh_token': tokens.get('refresh_token'),
        'token_uri': TOKEN_URI,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
    }

    # Store in session for linking step
    request.session['google_credentials'] = json.dumps(credentials_dict)

    # Clear OAuth session data
    if 'oauth_state' in request.session:
        del request.session['oauth_state']
    if 'code_verifier' in request.session:
        del request.session['code_verifier']

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
        return HttpResponse("No Google credentials in session. Please <a href='/auth/google/'>start OAuth flow again</a>.", status=400)

    try:
        user = JiraUser.objects.get(email=email)
    except JiraUser.DoesNotExist:
        # Create new user record with unique placeholder ID
        user = JiraUser.objects.create(
            email=email,
            jira_account_id=f'pending_{uuid.uuid4().hex[:16]}',  # Unique placeholder, updated on first sync
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
