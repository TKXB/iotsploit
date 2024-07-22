r'''
Copyright 2014 Google Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
'''
from http.server import BaseHTTPRequestHandler
from io  import StringIO
import http.client
import re
import io
from urllib import response


class HTTPRequest(BaseHTTPRequestHandler):
    """Basic RequestHandler to try and parse a given request_text as an HTTP request.

    """

    def __init__(self, request_text):
        # sometimes path and headers don't get set in the object, set some dummy
        # ones so we don't have to check for them elsewhere.
        self.path = ""
        self.headers = {}
        self.rfile = StringIO(request_text)
        self.raw_requestline = self.rfile.readline()
        self.error_code = self.error_message = None
        self.parse_request()

    def send_error(self, code, message):
        self.error_code = code
        self.error_message = message


class _FakeSocket(io.BytesIO):

    def makefile(self, *args, **kwargs):
        return self


def parse_request(request):
    """Try and parse request as an HTTP request.
    Returns a nogotofail.mitm.util.http.HTTPRequest if successful
    Returns None if request is not a HTTP request
    """
    # Sometimes HTTPRequest accepts weird things, so do a simple check for a
    # HTTP/.*\r\n before trying to parse
    if not re.match(b".*HTTP/.*\r\n", request):
        return None
    http = HTTPRequest(request)
    if http.error_code:
        return None
    return http


def parse_response(response):
    """Try and parse response as an HTTP response.
    Returns a httplib.http.HTTPResponse if sucessful
    Returns None if response is not a HTTP response
    """
    s = _FakeSocket(response)

    try:
        http_response = http.client.HTTPResponse(s)
        http_response.begin()
        return http_response 
    except http.client.HTTPException:
        return None
