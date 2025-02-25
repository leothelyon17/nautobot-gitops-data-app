# nautobot_client.py
import requests
from urllib.parse import urlparse
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class NautobotClient:
    def __init__(self, url: str, token: str | None = None, **kwargs):
        self.base_url = self._parse_url(url)
        self._token = token
        self.verify_ssl = kwargs.get("verify_ssl", False)
        self.retries = kwargs.get("retries", 3)
        self.timeout = kwargs.get("timeout", 10)
        self.proxies = kwargs.get("proxies", None)
        self._create_session()

    def _parse_url(self, url: str) -> str:
        parsed_url = urlparse(url)
        if not parsed_url.scheme:
            return f"http://{url}"
        return parsed_url.geturl()

    def _create_session(self):
        self.session = requests.Session()
        self.session.headers["Content-Type"] = "application/json"
        self.session.headers["Accept"] = "application/json"
        self.session.headers["Authorization"] = f"Token {self._token}"
        if self.proxies:
            self.session.proxies.update(self.proxies)
        retry_method = Retry(total=self.retries, backoff_factor=1, status_forcelist=[429,500,502,503,504])
        adapter = HTTPAdapter(max_retries=retry_method)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def http_call(self, method: str, url: str, data: dict = None,
                  json_data: dict = None, headers: dict = None,
                  verify: bool = False, params: dict = None) -> dict:
        _request = requests.Request(
            method=method.upper(),
            url=self.base_url + url,
            data=data,
            json=json_data,
            headers=headers,
            params=params,
        )
        _request = self.session.prepare_request(_request)
        _response = self.session.send(request=_request, verify=verify, timeout=self.timeout)
        if _response.status_code not in (200, 201, 204):
            raise Exception(f"API call to {self.base_url + url} returned status code {_response.status_code}")
        if _response.status_code == 204:
            return {}
        return _response.json()


