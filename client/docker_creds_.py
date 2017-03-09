# Copyright 2017 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""This package exposes credentials for talking to a Docker registry."""



import abc
import base64

import httplib2  # pylint: disable=unused-import
from oauth2client import client as oauth2client  # pylint: disable=unused-import


class Provider(object):
  """Interface for providing User Credentials for use with a Docker Registry."""

  __metaclass__ = abc.ABCMeta  # For enforcing that methods are overriden.

  @abc.abstractmethod
  def Get(self):
    """Produces a value suitable for use in the Authorization header."""


class Anonymous(Provider):
  """Implementation for anonymous access."""

  def Get(self):
    """Implement anonymous authentication."""
    return ''


class SchemeProvider(Provider):
  """Implementation for providing a challenge response credential."""

  def __init__(self, scheme):
    self._scheme = scheme

  @property
  @abc.abstractmethod
  def suffix(self):
    """Returns the authentication payload to follow the auth scheme."""

  def Get(self):
    """Gets the credential in a form suitable for an Authorization header."""
    return '%s %s' % (self._scheme, self.suffix)


class Basic(SchemeProvider):
  """Implementation for providing a username/password-based creds."""

  def __init__(self, username, password):
    super(Basic, self).__init__('Basic')
    self._username = username
    self._password = password

  @property
  def username(self):
    return self._username

  @property
  def password(self):
    return self._password

  @property
  def suffix(self):
    return base64.b64encode(self.username + ':' + self.password)

_USERNAME = '_token'


class OAuth2(Basic):
  """Base class for turning OAuth2Credentials into suitable GCR credentials."""

  def __init__(
      self,
      creds,
      transport):
    """Constructor.

    Args:
      creds: the credentials from which to retrieve access tokens.
      transport: the http transport to use for token exchanges.
    """
    super(OAuth2, self).__init__(_USERNAME, 'does not matter')
    self._creds = creds
    self._transport = transport

  @property
  def password(self):
    # WORKAROUND...
    # The python oauth2client library only loads the credential from an
    # on-disk cache the first time 'refresh()' is called, and doesn't
    # actually 'Force a refresh of access_token' as advertised.
    # This call will load the credential, and the call below will refresh
    # it as needed.  If the credential is unexpired, the call below will
    # simply return a cache of this refresh.
    unused_at = self._creds.get_access_token(http=self._transport)

    # Most useful API ever:
    # https://www.googleapis.com/oauth2/v1/tokeninfo?access_token={at}
    return self._creds.get_access_token(http=self._transport).access_token
