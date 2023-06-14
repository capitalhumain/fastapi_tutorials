from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from starlette.config import Config
from starlette.requests import Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from authlib.integrations.starlette_client import OAuth
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# Initialize FastAPI
app = FastAPI(docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key='!secret')


# --- Main ---


@app.get('/')
async def home(request: Request):
    # Try to get the user
    user = request.session.get('user')
    if user is not None:
        email = user['email']
        html = (
            f'<pre>Email: {email}</pre><br>'
            '<a href="/docs">documentation</a><br>'
            '<a href="/logout">logout</a>'
        )
        return HTMLResponse(html)

    # Show the login link
    return HTMLResponse('<a href="/login">login</a>')


# --- Google OAuth ---


# Initialize our OAuth instance from the client ID and client secret specified in our .env file
config = Config('.env')
oauth = OAuth(config)

CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
oauth.register(
    name='google',
    server_metadata_url=CONF_URL,
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/webmasters.readonly'
    }
)
"""oauth.register(
    'google',
    client_id='1075021919607-ef54410eb57bbk89a04ji41ebsvvhqb5.apps.googleusercontent.com',
    client_secret='9cYgtBjIsiXTWdIkO5aaz9d0',
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/webmasters.readonly'
    }
)"""

@app.get('/login', tags=['authentication'])  # Tag it as "authentication" for our docs
async def login(request: Request):
    # Redirect Google OAuth back to our application
    redirect_uri = request.url_for('auth')

    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.route('/auth')
async def auth(request: Request):
    # Perform Google OAuth
    token = await oauth.google.authorize_access_token(request)
    user = await oauth.google.parse_id_token(request, token)

    # Save the user
   
    request.session['user'] = dict(user)

    return RedirectResponse(url='/')


@app.get('/logout', tags=['authentication'])  # Tag it as "authentication" for our docs
async def logout(request: Request):
    # Remove the user
    request.session.pop('user', None)

    return RedirectResponse(url='/')


# --- Dependencies ---


# Try to get the logged in user
async def get_user(request: Request) -> Optional[dict]:
    user = request.session.get('user')
    if user is not None:
        return user
    else:
        raise HTTPException(status_code=403, detail='Could not validate credentials.')

    return None


# --- Documentation ---


@app.route('/openapi.json')
async def get_open_api_endpoint(request: Request, user: Optional[dict] = Depends(get_user)):  # This dependency protects our endpoint!
    response = JSONResponse(get_openapi(title='FastAPI', version=1, routes=app.routes))
    return response


@app.get('/docs', tags=['documentation'])  # Tag it as "documentation" for our docs
async def get_documentation(request: Request, user: Optional[dict] = Depends(get_user)):  # This dependency protects our endpoint!
    response = get_swagger_ui_html(openapi_url='/openapi.json', title='Documentation')
    return response


@app.get('/protected')
async def protected(user: Optional[dict] = Depends(get_user)):
    # print(user)
    if user is None:
        raise HTTPException(status_code=403, detail='Could not validate credentials.')
        
    creds = Credentials(
        token=user['token']['access_token'],
        refresh_token=user['token']['refresh_token'],
        token_uri=CONF_URL,
        client_id=oauth.google.client_id,
        client_secret=oauth.google.client_secret
    )
    
    searchconsole = build('searchconsole', 'v1', credentials=creds)
    request = {
        "startDate": '2023-01-01',
        "endDate": '2023-01-31',
        "dimensions": ["searchAppearance"],
        "rowLimit": 10,
    }
    results = execute_request(searchconsole, 'https://www.inpixio.com', request)
    """results = searchconsole.searchanalytics().query().get(
        siteUrl='https://example.com',
        startDate='2020-01-01',
        endDate='2020-01-31'
    ).execute()"""
    
    return results 

def execute_request(service, property_uri, request):
    """Executes a searchAnalytics.query request.

    Args:
      service: The searchconsole service to use when executing the query.
      property_uri: The site or app URI to request data for.
      request: The request to be executed.

    Returns:
      An array of response rows.
    """
    return service.searchanalytics().query(siteUrl=property_uri, body=request).execute()

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000, log_level='debug')
