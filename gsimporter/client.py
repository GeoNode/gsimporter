import os
import json
import pprint
import logging
import urllib3
import mimetypes
from six import string_types
from gsimporter.api import (RequestFailed,
                            BadRequest,
                            NotFound,
                            parse_response)

try:
    from urllib.parse import urlparse, urlencode
except ImportError:  # python2 compatible
    from urlparse import urlparse
    from urllib import urlencode

from . import _util

_logger = logging.getLogger(__name__)


class Client(object):

    def __init__(self, url, username=None, password=None):
        self.username = username or 'admin'
        self.password = password or 'geoserver'
        self.client = _Client(url, self.username, self.password)

    def _call(self, fun, *args):
        # call the provided function and set the _uploader field on each
        # of the returned api objects
        robj = fun(*args)
        if isinstance(robj, list):
            for i in robj:
                i._uploader = self
        else:
            robj._uploader = self
        return robj

    def get_sessions(self):
        '''Get an 'unexpanded' list of a imports - the Session objects returned
        will not have any details beside their id and href.
        :return a list of Session objects
        '''
        return self._call(self.client.get_imports)

    def get_session(self, id):
        '''Get an existing 'expanded' session by id.
        :param id: the integer id of the session to get
        :return: an expanded Session object
        '''
        return self._call(self.client.get_import, id)

    def start_import(self, import_id=None, mosaic=False, name=None, target_store=None, charset_encoding="UTF-8"):
        """Create a new import session.
        :param import_id: optional id to specify
        :param mosaic: if True, indicates a mosaic upload
        :param name: if provided, name the mosaic upload
        :param target_store: if provided, name of an existing store to be updated
        :param charsetEncoding: if provided, the charsetEncoding to use (default UTF-8)
        :returns: a gsimporter.api.Session object
        """
        session = self._call(self.client.start_import, import_id,
                             mosaic, name, target_store, charset_encoding)
        if import_id: assert session.id >= import_id
        return session

    def upload(self, fpath, use_url=False, import_id=None, mosaic=False,
               initial_opts=None):
        """Try a complete import - create a session and upload the provided file.
        fpath can be a path to a zip file or the 'main' file if a shapefile or
        a tiff.
        :param fpath: path to file or zip
        :param use_url: if True, tell the importer where to find the file
        :param import_id: if provided, use as the specified id
        :param mosaic: if True, indicates a mosaic upload
        :param initial_opts: default None, dict of initial import options
        :returns: a gsimporter.api.Session object
        """
        files = [fpath]
        if fpath.lower().endswith(".shp"):
            files = _util.shp_files(fpath)

        return self.upload_files(files, use_url, import_id, mosaic, initial_opts)

    def upload_files(self, files, use_url=False, import_id=None, mosaic=False,
                     name=None, intial_opts=None, target_store=None, charset_encoding="UTF-8"):
        """Upload the provided files. If a mosaic, compute a name from the
        provided files.
        :param files: the files to upload
        :param use_url: if True, tell the importer where to find the file
        :param import_id: if provided, use as the specified id
        :param mosaic: if True, indicates a mosaic upload
        :param initial_opts: default None, dict of initial import options
        :returns: a gsimporter.api.Session object
        """
        if mosaic and not name:
            # @hack - ensure that target layer gets a nice name
            layername = os.path.basename(files[0])
            name, _ = os.path.splitext(layername)
        if target_store and not name:
            name = os.path.basename(files[0])

        session = self.start_import(
            import_id,
            mosaic=mosaic,
            name=name,
            target_store=target_store,
            charset_encoding=charset_encoding)

        if files:
            session.upload_task(files, use_url, intial_opts)

        return session

    # pickle protocol - client object cannot be serialized
    # this allows api objects to be seamlessly pickled and loaded without restarting
    # the connection more explicitly but this will have consequences if other state is stored
    # in the uploader or client objects

    def __getstate__(self):
        cl = self.client
        return {'url': cl.service_url, 'username': cl.username, 'password': cl.password}

    def __setstate__(self, state):
        self.client = _Client(state['url'], state['username'], state['password'])


class _Client(object):
    """Lower level http client"""

    def __init__(self, url, username, password):
        self.service_url = url
        self.service_scheme = urlparse(url).scheme
        if self.service_url.endswith("/"):
            self.service_url = self.service_url.strip("/")
        self.username = username
        self.password = password
        if self.service_scheme == 'https':
            self.http = urllib3.PoolManager(
                2,
                maxsize=4,
                block=True,
                cert_reqs='CERT_NONE',
                assert_hostname=False)
        else:
            self.http = urllib3.PoolManager(
                2,
                maxsize=4,
                block=True)

        self.headers = urllib3.util.make_headers(basic_auth=':'.join([username, password]))

    def url(self, path=None):
        if path:
            return "%s/%s" % (self.service_url, path)
        return self.service_url

    def post(self, url):
        return self._request(url, "POST")

    def delete(self, url):
        return self._request(url, "DELETE")

    def put_json(self, url, data):
        return self._request(url, "PUT", data, {
            "Content-type": "application/json"
        })

    def _parse_errors(self, content):
        try:
            resp = json.loads(content)
        except ValueError:
            return [content]
        return resp['errors']

    def _request(self, url, method="GET", data=None, headers={}):
        log_data = None
        if data:
            try:
                data_len = len(data)
            except:
                data_len = -1
            log_data = data if data_len < 1024 else "[Data to long...]"
        _logger.info("%s request to %s:\n[Data]:%s", method, url, log_data)
        headers.update(self.headers)
        resp = self.http.request(method, url, body=data, headers=headers, preload_content=False)
        content = resp.read()
        headers = resp.headers
        _debug(headers, content)
        if resp.status == 404:
            raise NotFound()
        if resp.status < 200 or resp.status > 299:
            if resp.status == 400:
                raise BadRequest(*self._parse_errors(content))
            raise RequestFailed(resp.status, content)
        return resp, content

    def post_upload_url(self, url, upload_url):
        data = urlencode({
            'url': upload_url
        })
        return self._request(url, "POST", data, {
            # importer very picky
            'Content-type': "application/x-www-form-urlencoded"
        })

    def put_zip(self, url, payload):
        message = open(payload)
        with message:
            return self._request(url, "PUT", message, {
                "Content-type": "application/zip",
            })

    def get_import(self, i):
        return parse_response(self._request(self.url("imports/%s?expand=3" % i)))

    def get_imports(self):
        return parse_response(self._request(self.url("imports")))

    def start_import(self, import_id=None, mosaic=False, name=None, target_store=False, charset_encoding="UTF-8"):
        method = 'POST'
        data = None
        headers = {}
        import_data = {}
        if mosaic:
            import_data = {"import": {
                "data": {
                   "type": "mosaic",
                   "name": name,
                   "time": {
                        "mode": "auto"
                   },
                   "charsetEncoding": charset_encoding
                }
            }}
        elif target_store:
            import_data = {"import": {
                "data": {
                    "type": "file",
                    "file": name,
                    "charsetEncoding": charset_encoding
                },
                "targetStore": {
                   "dataStore": {
                        "name": target_store
                   }
                }
            }}
        else:
            import_data = {"import": {
                "data": {
                    "type": "file",
                    "file": name,
                    "charsetEncoding": charset_encoding
                }
            }}
        data = json.dumps(import_data)
        headers["Content-type"] = "application/json"
        if import_id is not None:
            url = self.url("imports/%s" % import_id)
            method = 'PUT'
        else:
            url = self.url("imports")
        return parse_response(self._request(url, method, data, headers))

    def post_multipart(self, url, files, fields=[]):
        """
        fields is a sequence of (name, value) elements for regular form fields.
        files is a sequence of name or (name,filename) or (name, filename, value)
        elements for data to be uploaded as files
        """
        BOUNDARY = '----------ThIs_Is_tHe_bouNdaRY_$'
        CRLF = '\r\n'
        L = []
        _logger.info("post_multipart %s %s %s", url, files, fields)
        for (key, value) in fields:
            L.append('--' + BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"' % str(key))
            L.append('')
            L.append(str(value))
        for fpair in files:
            try:
                if isinstance(fpair, string_types):
                    fpair = (fpair, fpair)
            except BaseException:
                if isinstance(fpair, str):
                    fpair = (fpair, fpair)
            key = fpair[0]
            if len(fpair) == 2:
                filename = os.path.basename(fpair[1])
                fp = open(fpair[1], 'rb')
                value = fp.read()
                fp.close()
            else:
                filename, value = fpair[1:]
            L.append('--' + BOUNDARY)
            L.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (str(key), str(filename)))
            L.append('Content-Type: %s' % str(_get_content_type(filename)))
            L.append('')
            L.append(value.decode('ISO-8859-1'))
        L.append('--' + BOUNDARY + '--')
        L.append('')
        return self._request(
            url, 'POST', CRLF.join(L), {
                'Content-Type': 'multipart/form-data; boundary=%s' % BOUNDARY
            }
        )


def _get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def _debug(resp, content):
    if _logger.isEnabledFor(logging.DEBUG):
        _logger.debug("response: %s", pprint.pformat(resp))
        if "content-type" in resp and resp['content-type'] == 'application/json':
            try:
                content = json.loads(content)
                content = json.dumps(content, indent=2)
            except ValueError:
                pass

        _logger.debug("content : %s", content)
