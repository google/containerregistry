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

"""This package provides DockerImageList for examining Manifest Lists."""



import abc
import httplib
import json

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2_2 import docker_digest
from containerregistry.client.v2_2 import docker_http
from containerregistry.client.v2_2 import docker_image as v2_2_image
import httplib2


class DigestMismatchedError(Exception):
  """Exception raised when a digest mismatch is encountered."""


class InvalidMediaTypeError(Exception):
  """Exception raised when an invalid media type is encountered."""


class Platform(object):
  """Represents runtime requirements for an image.

  See: https://docs.docker.com/registry/spec/manifest-v2-2/#manifest-list
  """

  def __init__(self, content=None):
    self._content = content or {}

  def architecture(self):
    return self._content.get('architecture', 'amd64')

  def os(self):
    return self._content.get('os', 'linux')

  def os_version(self):
    return self._content.get('os.version')

  def os_features(self):
    return set(self._content.get('os.features', []))

  def variant(self):
    return self._content.get('variant')

  def features(self):
    return set(self._content.get('features', []))

  def can_run(self, required):
    """Returns True if this platform can run the 'required' platform."""
    if not required:
      # Some images don't specify 'platform', assume they can always run.
      return True

    # Required fields.
    if required.architecture() != self.architecture():
      return False
    if required.os() != self.os():
      return False

    # Optional fields.
    if required.os_version() and required.os_version() != self.os_version():
      return False
    if required.variant() and required.variant() != self.variant():
      return False

    # Verify any required features are a subset of this platform's features.
    if required.os_features() and not required.os_features().issubset(
        self.os_features()):
      return False
    if required.features() and not required.features().issubset(
        self.features()):
      return False

    return True

  def compatible_with(self, target):
    """Returns True if this platform can run on the 'target' platform."""
    return target.can_run(self)

  def __iter__(self):
    return iter(self._content)


class DockerImageList(object):
  """Interface for implementations that interact with Docker manifest lists."""

  __metaclass__ = abc.ABCMeta  # For enforcing that methods are overridden.

  def digest(self):
    """The digest of the manifest."""
    return docker_digest.SHA256(self.manifest())

  def media_type(self):
    """The media type of the manifest."""
    manifest = json.loads(self.manifest())
    # Since 'mediaType' is optional for OCI images, assume OCI if it's missing.
    return manifest.get('mediaType', docker_http.OCI_IMAGE_INDEX_MIME)

  # pytype: disable=bad-return-type
  @abc.abstractmethod
  def manifest(self):
    """The JSON manifest referenced by the tag/digest.

    Returns:
      The raw json manifest
    """
  # pytype: enable=bad-return-type

  # pytype: disable=bad-return-type
  @abc.abstractmethod
  def resolve_all(
      self, target=None):
    """Resolves a manifest list to a list of compatible manifests.

    Args:
      target: the platform to check for compatibility. If omitted, the target
          platform defaults to linux/amd64.

    Returns:
      A list of images that can be run on the target platform.
    """
  # pytype: enable=bad-return-type

  def resolve(self, target=None):
    """Resolves a manifest list to a compatible manifest.

    Args:
      target: the platform to check for compatibility. If omitted, the target
          platform defaults to linux/amd64.

    Raises:
      Exception: no manifests were compatible with the target platform.

    Returns:
      An image that can run on the target platform.
    """
    if not target:
      target = Platform()
    images = self.resolve_all(target)
    if not images:
      raise Exception('Could not resolve manifest list to compatible manifest')
    return images[0]

  # __enter__ and __exit__ allow use as a context manager.
  @abc.abstractmethod
  def __enter__(self):
    """Open the image for reading."""

  @abc.abstractmethod
  def __exit__(self, unused_type, unused_value, unused_traceback):
    """Close the image."""

  @abc.abstractmethod
  def __iter__(self):
    """Iterate over this manifest list's children."""


class FromRegistry(DockerImageList):
  """This accesses a docker image list hosted on a registry (non-local)."""

  def __init__(
      self,
      name,
      basic_creds,
      transport,
      accepted_mimes=docker_http.MANIFEST_LIST_MIMES):
    self._name = name
    self._creds = basic_creds
    self._original_transport = transport
    self._accepted_mimes = accepted_mimes
    self._response = {}

  def _content(
      self,
      suffix,
      accepted_mimes=None,
      cache=True
  ):
    """Fetches content of the resources from registry by http calls."""
    if isinstance(self._name, docker_name.Repository):
      suffix = '{repository}/{suffix}'.format(
          repository=self._name.repository,
          suffix=suffix)

    if suffix in self._response:
      return self._response[suffix]

    _, content = self._transport.Request(
        '{scheme}://{registry}/v2/{suffix}'.format(
            scheme=docker_http.Scheme(self._name.registry),
            registry=self._name.registry,
            suffix=suffix),
        accepted_codes=[httplib.OK],
        accepted_mimes=accepted_mimes)
    if cache:
      self._response[suffix] = content
    return content

  def images(self):
    """Returns a list of tuples whose elements are (name, platform, image).

    Raises:
      InvalidMediaTypeError: a child with an unexpected media type was found.
    """
    manifests = json.loads(self.manifest())['manifests']
    results = []
    for entry in manifests:
      digest = entry['digest']
      name = docker_name.Digest('{base}@{digest}'.format(
          base=self._name.as_repository(), digest=digest))

      # TODO(user): Support Image Index.
      if entry['mediaType'] == docker_http.MANIFEST_LIST_MIME:
        image = FromRegistry(name, self._creds, self._original_transport)
      elif entry['mediaType'] == docker_http.MANIFEST_SCHEMA2_MIME:
        image = v2_2_image.FromRegistry(name, self._creds,
                                        self._original_transport)
      else:
        raise InvalidMediaTypeError('Invalid media type: ' + entry['mediaType'])

      platform = Platform(entry['platform']) if 'platform' in entry else None
      results.append((name, platform, image))
    return results

  def resolve_all(
      self, target=None):
    results = []
    images = self.images()
    # Sort by name for deterministic output.
    images.sort(key=lambda (name, platform, image): str(name))
    for _, platform, image in images:
      # Recurse on manifest lists.
      if isinstance(image, DockerImageList):
        with image:
          results.extend(image.resolve_all(target))
      elif target.can_run(platform):
        results.append(image)
    return results

  def exists(self):
    try:
      manifest = json.loads(self.manifest(validate=False))
      return manifest['schemaVersion'] == 2 and 'manifests' in manifest
    except docker_http.V2DiagnosticException as err:
      if err.status == httplib.NOT_FOUND:
        return False
      raise

  def manifest(self, validate=True):
    """Override."""
    # GET server1/v2/<name>/manifests/<tag_or_digest>

    if isinstance(self._name, docker_name.Tag):
      return self._content('manifests/' + self._name.tag, self._accepted_mimes)
    else:
      assert isinstance(self._name, docker_name.Digest)
      c = self._content('manifests/' + self._name.digest, self._accepted_mimes)
      computed = docker_digest.SHA256(c)
      if validate and computed != self._name.digest:
        raise DigestMismatchedError(
            'The returned manifest\'s digest did not match requested digest, '
            '%s vs. %s' % (self._name.digest, computed))
      return c

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    # Create a v2 transport to use for making authenticated requests.
    self._transport = docker_http.Transport(
        self._name, self._creds, self._original_transport, docker_http.PULL)

    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass

  def __str__(self):
    return '<docker_image_list.FromRegistry name: {}>'.format(str(self._name))

  def __iter__(self):
    return iter(self.images())


class FromList(DockerImageList):
  """This synthesizes a Manifest List from a list of images."""

  def __init__(self,
               images,
               name=None):
    self._images = images
    self._name = name

  def manifest(self):
    list_body = {
        'mediaType': docker_http.MANIFEST_LIST_MIME,
        'schemaVersion': 2,
        'manifests': []
    }

    for (platform, manifest) in self._images:
      manifest_body = {
          'digest': manifest.digest(),
          'mediaType': manifest.media_type(),
          'size': len(manifest.manifest())
      }

      if platform:
        manifest_body['platform'] = dict(platform)
      list_body['manifests'].append(manifest_body)
    return json.dumps(list_body, sort_keys=True)

  def resolve_all(
      self, target=None):
    """Resolves a manifest list to a list of compatible manifests.

    Args:
      target: the platform to check for compatibility. If omitted, the target
          platform defaults to linux/amd64.

    Returns:
      A list of images that can be run on the target platform.
    """
    results = []
    for (platform, image) in self._images:
      if target.can_run(platform):
        results.append(image)
    return results

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass

  def __iter__(self):
    results = []
    for (platform, manifest) in self._images:
      name = docker_name.Digest('{base}@{digest}'.format(
          base=self._name.as_repository(), digest=manifest.digest()))
      results.append((name, platform, manifest))
    return iter(results)
