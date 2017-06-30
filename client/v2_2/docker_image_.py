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

"""This package provides DockerImage for examining docker_build outputs."""



import abc
import cStringIO
import gzip
import hashlib
import httplib
import json
import os
import tarfile
import threading

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2_2 import docker_http
from containerregistry.client.v2_2 import util
import httplib2


class DigestMismatchedError(Exception):
  """Exception raised when a digest mismatch is encountered."""


class DockerImage(object):
  """Interface for implementations that interact with Docker images."""

  __metaclass__ = abc.ABCMeta  # For enforcing that methods are overriden.

  def fs_layers(self):
    """The ordered collection of filesystem layers that comprise this image."""
    manifest = json.loads(self.manifest())
    return [x['digest'] for x in reversed(manifest['layers'])]

  def config_blob(self):
    manifest = json.loads(self.manifest())
    return manifest['config']['digest']

  def blob_set(self):
    """The unique set of blobs that compose to create the filesystem."""
    return set(self.fs_layers() + [self.config_blob()])

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
  def config_file(self):
    """The raw blob string of the config file."""
  # pytype: enable=bad-return-type

  def blob_size(self, digest):
    """The byte size of the raw blob."""
    return len(self.blob(digest))

  # pytype: disable=bad-return-type
  @abc.abstractmethod
  def blob(self, digest):
    """The raw blob of the layer.

    Args:
      digest: the 'algo:digest' of the layer being addressed.

    Returns:
      The raw blob string of the layer.
    """
  # pytype: enable=bad-return-type

  def uncompressed_blob(self, digest):
    """Same as blob() but uncompressed."""
    zipped = self.blob(digest)
    buf = cStringIO.StringIO(zipped)
    f = gzip.GzipFile(mode='rb', fileobj=buf)
    unzipped = f.read()
    return unzipped

  # __enter__ and __exit__ allow use as a context manager.
  @abc.abstractmethod
  def __enter__(self):
    """Open the image for reading."""

  @abc.abstractmethod
  def __exit__(self, unused_type, unused_value, unused_traceback):
    """Close the image."""


class FromRegistry(DockerImage):
  """This accesses a docker image hosted on a registry (non-local)."""

  def __init__(
      self,
      name,
      basic_creds,
      transport):
    self._name = name
    self._creds = basic_creds
    self._original_transport = transport
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

  def _tags(self):
    # See //cloud/containers/registry/proto/v2/tags.proto
    # for the full response structure.
    return json.loads(self._content('tags/list'))

  def tags(self):
    return self._tags().get('tags', [])

  def manifests(self):
    payload = self._tags()
    if 'manifest' not in payload:
      # Only GCR supports this schema.
      return {}
    return payload['manifest']

  def children(self):
    payload = self._tags()
    if 'child' not in payload:
      # Only GCR supports this schema.
      return []
    return payload['child']

  def exists(self):
    try:
      manifest = json.loads(self.manifest(validate=False))
      return manifest['schemaVersion'] == 2
    except docker_http.V2DiagnosticException as err:
      if err.status == httplib.NOT_FOUND:
        return False
      raise

  def manifest(self, validate=True):
    """Override."""
    # GET server1/v2/<name>/manifests/<tag_or_digest>
    accepted_mimes = docker_http.MANIFEST_SCHEMA2_MIMES

    if isinstance(self._name, docker_name.Tag):
      return self._content('manifests/' + self._name.tag, accepted_mimes)
    else:
      assert isinstance(self._name, docker_name.Digest)
      c = self._content('manifests/' + self._name.digest, accepted_mimes)
      computed = util.Digest(c)
      if validate and computed != self._name.digest:
        raise DigestMismatchedError(
            'The returned manifest\'s digest did not match requested digest, '
            '%s vs. %s' % (self._name.digest, computed))
      return c

  def config_file(self):
    """Override."""
    return self.blob(self.config_blob())

  def blob_size(self, digest):
    """The byte size of the raw blob."""
    suffix = 'blobs/' + digest
    if isinstance(self._name, docker_name.Repository):
      suffix = '{repository}/{suffix}'.format(
          repository=self._name.repository,
          suffix=suffix)

    resp, unused_content = self._transport.Request(
        '{scheme}://{registry}/v2/{suffix}'.format(
            scheme=docker_http.Scheme(self._name.registry),
            registry=self._name.registry,
            suffix=suffix),
        method='HEAD',
        accepted_codes=[httplib.OK])

    return int(resp['content-length'])

  # Large, do not memoize.
  def blob(self, digest):
    """Override."""
    # GET server1/v2/<name>/blobs/<digest>
    c = self._content('blobs/' + digest, cache=False)
    computed = 'sha256:' + hashlib.sha256(c).hexdigest()
    if digest != computed:
      raise DigestMismatchedError(
          'The returned content\'s digest did not match its content-address, '
          '%s vs. %s' % (digest, computed if c else '(content was empty)'))
    return c

  def catalog(self, page_size=100):
    # TODO(user): Handle docker_name.Repository for /v2/<name>/_catalog
    if isinstance(self._name, docker_name.Repository):
      raise ValueError('Expected docker_name.Registry for "name"')

    url = '{scheme}://{registry}/v2/_catalog?n={page_size}'.format(
        scheme=docker_http.Scheme(self._name.registry),
        registry=self._name.registry,
        page_size=page_size)

    for _, content in self._transport.PaginatedRequest(
        url, accepted_codes=[httplib.OK]):
      wrapper_object = json.loads(content)

      if 'repositories' not in wrapper_object:
        raise docker_http.BadStateException(
            'Malformed JSON response: %s' % content)

      # TODO(user): This should return docker_name.Repository
      for repo in wrapper_object['repositories']:
        yield repo

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    # Create a v2 transport to use for making authenticated requests.
    self._transport = docker_http.Transport(
        self._name, self._creds, self._original_transport, docker_http.PULL)

    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass


# Gzip injects a timestamp into its output, which makes its output and digest
# non-deterministic.  To get reproducible pushes, freeze time.
# This approach is based on the following StackOverflow answer:
# http://stackoverflow.com/
#    questions/264224/setting-the-gzip-timestamp-from-python
class _FakeTime(object):

  def time(self):
    return 1225856967.109

gzip.time = _FakeTime()


class FromTarball(DockerImage):
  """This decodes the image tarball output of docker_build for upload."""

  def __init__(
      self,
      tarball,
      name=None,
      compresslevel=9,
  ):
    self._tarball = tarball
    self._compresslevel = compresslevel
    self._memoize = {}
    self._lock = threading.Lock()
    self._name = name
    self._manifest = None
    self._blob_names = None

  def _content(self, name, memoize=True):
    """Fetches a particular path's contents from the tarball."""
    # Check our cache
    if memoize:
      with self._lock:
        if name in self._memoize:
          return self._memoize[name]

    # tarfile is inherently single-threaded:
    # https://mail.python.org/pipermail/python-bugs-list/2015-March/265999.html
    # so instead of locking, just open the tarfile for each file
    # we want to read.
    with tarfile.open(name=self._tarball, mode='r') as tar:
      try:
        content = tar.extractfile(name).read()
      except KeyError:
        content = tar.extractfile('./' + name).read()

      # Populate our cache.
      if memoize:
        with self._lock:
          self._memoize[name] = content
      return content

  def _gzipped_content(self, name):
    """Returns the result of _content with gzip applied."""
    unzipped = self._content(name, memoize=False)
    buf = cStringIO.StringIO()
    f = gzip.GzipFile(mode='wb', compresslevel=self._compresslevel, fileobj=buf)
    try:
      # If we are applying gzip, probability is high this could be large,
      # so do not memoize.
      f.write(unzipped)
    finally:
      f.close()
    zipped = buf.getvalue()
    return zipped

  def _populate_manifest_and_blobs(self):
    """Populates self._manifest and self._blob_names."""
    manifest = {
        'mediaType': docker_http.MANIFEST_SCHEMA2_MIME,
        'schemaVersion': 2,
        'config': {
            'digest': 'sha256:' + hashlib.sha256(
                self.config_file()).hexdigest(),
            'mediaType': docker_http.CONFIG_JSON_MIME,
            'size': len(self.config_file())
        },
        'layers': [
            # Populated below
        ]
    }

    blob_names = {}
    for layer in self._layers:
      content = self._gzipped_content(layer)
      name = 'sha256:' + hashlib.sha256(content).hexdigest()
      blob_names[name] = layer
      manifest['layers'].append({
          'digest': name,
          # TODO(user): Do we need to sniff the file to detect this?
          'mediaType': docker_http.LAYER_MIME,
          'size': len(content),
      })

    with self._lock:
      self._manifest = manifest
      self._blob_names = blob_names

  def manifest(self):
    """Override."""
    if not self._manifest:
      self._populate_manifest_and_blobs()
    return json.dumps(self._manifest, sort_keys=True)

  def config_file(self):
    """Override."""
    return self._content(self._config_file)

  # Could be large, do not memoize
  def uncompressed_blob(self, digest):
    """Override."""
    if not self._blob_names:
      self._populate_manifest_and_blobs()
    return self._content(self._blob_names[digest],  # pytype: disable=none-attr
                         memoize=False)

  # Could be large, do not memoize
  def blob(self, digest):
    """Override."""
    if not self._blob_names:
      self._populate_manifest_and_blobs()
    return self._gzipped_content(
        self._blob_names[digest])  # pytype: disable=none-attr

  def _resolve_tag(self):
    """Resolve the singleton tag this tarball contains using legacy methods."""
    repositories = json.loads(self._content('repositories', memoize=False))
    if len(repositories) != 1:
      raise ValueError('Tarball must contain a single repository, '
                       'or a name must be specified to FromTarball.')

    for (repo, tags) in repositories.iteritems():
      if len(tags) != 1:
        raise ValueError('Tarball must contain a single tag, '
                         'or a name must be specified to FromTarball.')
      for (tag, unused_layer) in tags.iteritems():
        return '{repository}:{tag}'.format(repository=repo, tag=tag)

    raise Exception('unreachable')

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    manifest_json = self._content('manifest.json')
    manifest_list = json.loads(manifest_json)

    config = None
    layers = []
    # Find the right entry, either:
    # 1) We were supplied with an image name, which we must find in an entry's
    #   RepoTags, or
    # 2) We were not supplied with an image name, and this must have a single
    #   image defined.
    if len(manifest_list) != 1:
      if not self._name:
        # If we run into this situation, fall back on the legacy repositories
        # file to tell us the single tag.  We do this because Bazel will apply
        # build targets as labels, so each layer will be labelled, but only
        # the final label will appear in the resulting repositories file.
        self._name = self._resolve_tag()

    for entry in manifest_list:
      if not self._name or str(self._name) in entry.get('RepoTags', []):
        config = entry.get('Config')
        layers = entry.get('Layers', [])

    if not config:
      raise ValueError('Unable to find %s in provided tarball.' % self._name)

    # Metadata from the tarball's configuration we need to construct the image.
    self._config_file = config
    self._layers = layers

    # We populate "manifest" and "blobs" lazily for two reasons:
    # 1) Allow use of this library for reading the config_file() from the image
    #   layer shards Bazel produces.
    # 2) Performance of the case where all we read is the config_file().

    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass


class FromDisk(DockerImage):
  """This accesses a more efficient on-disk format than FromTarball.

  FromDisk reads an on-disk format optimized for use with push and pull.

  It is expected that the number of layers in config_file's rootfs.diff_ids
  matches: count(legacy_base.layers) + len(layers).

  Layers are drawn from legacy_base first (it is expected to be the base),
  and then from layers.

  This is effectively the dual of the save.fast method, and is intended for use
  with Bazel's rules_docker.

  Args:
    config_file: the contents of the config file.
    layers: a list of pairs.  The first element is the path to a file containing
        the second element's sha256.  The second element is the .tar.gz of a
        filesystem layer.  These are ordered as they'd appear in the manifest.
    legacy_base: Optionally, the path to a legacy base image in FromTarball form
  """

  def __init__(
      self,
      config_file,
      layers,
      legacy_base=None
  ):
    self._config = config_file
    self._layers = []
    self._layer_to_filename = {}
    for (name_file, content_file) in layers:
      with open(name_file, 'r') as reader:
        layer_name = 'sha256:' + reader.read()
      self._layers.append(layer_name)
      self._layer_to_filename[layer_name] = content_file

    self._legacy_base = None
    if legacy_base:
      with FromTarball(legacy_base) as base:
        self._legacy_base = base

  def manifest(self):
    """Override."""
    return self._manifest

  def config_file(self):
    """Override."""
    return self._config

  # Could be large, do not memoize
  def uncompressed_blob(self, digest):
    """Override."""
    if digest not in self._layer_to_filename:
      # Leverage the FromTarball fast-path.
      return self._legacy_base.uncompressed_blob(digest)
    return super(FromDisk, self).uncompressed_blob(digest)

  # Could be large, do not memoize
  def blob(self, digest):
    """Override."""
    if digest not in self._layer_to_filename:
      return self._legacy_base.blob(digest)
    with open(self._layer_to_filename[digest], 'r') as reader:
      return reader.read()

  def blob_size(self, digest):
    """Override."""
    if digest not in self._layer_to_filename:
      return self._legacy_base.blob_size(digest)
    info = os.stat(self._layer_to_filename[digest])
    return info.st_size

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    base_layers = []
    if self._legacy_base:
      base_layers = json.loads(self._legacy_base.manifest())['layers']
    self._manifest = json.dumps({
        'schemaVersion': 2,
        'mediaType': docker_http.MANIFEST_SCHEMA2_MIME,
        'config': {
            'mediaType': docker_http.CONFIG_JSON_MIME,
            'size': len(self.config_file()),
            'digest': 'sha256:' + hashlib.sha256(self.config_file()).hexdigest()
        },
        'layers': base_layers + [
            {
                'mediaType': docker_http.LAYER_MIME,
                'size': self.blob_size(digest),
                'digest': digest
            }
            for digest in self._layers
        ]
    }, sort_keys=True)

    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass


def _in_whiteout_dir(
    fs,
    name
):
  while name:
    dirname = os.path.dirname(name)
    if name == dirname:
      break
    if fs.get(dirname):
      return True
    name = dirname
  return False

_WHITEOUT_PREFIX = '.wh.'


def extract(image, tar):
  """Extract the final filesystem from the image into tar.

  Args:
    image: a docker image whose final filesystem to construct.
    tar: the tarfile into which we are writing the final filesystem.
  """
  # Maps all of the files we have already added (and should never add again)
  # to whether they are a tombstone or not.
  fs = {}

  # Walk the layers, topmost first and add files.  If we've seen them in a
  # higher layer then we skip them.
  for layer in image.fs_layers():
    buf = cStringIO.StringIO(image.blob(layer))
    with tarfile.open(mode='r:gz', fileobj=buf) as layer_tar:
      for member in layer_tar.getmembers():
        # If we see a whiteout file, then don't add anything to the tarball
        # but ensure that any lower layers don't add a file with the whited
        # out name.
        basename = os.path.basename(member.name)
        dirname = os.path.dirname(member.name)
        tombstone = basename.startswith(_WHITEOUT_PREFIX)
        if tombstone:
          basename = basename[len(_WHITEOUT_PREFIX):]

        # Before adding a file, check to see whether it (or its whiteout) have
        # been seen before.
        name = os.path.normpath(os.path.join('.', dirname, basename))
        if name in fs:
          continue

        # Check for a whited out parent directory
        if _in_whiteout_dir(fs, name):
          continue

        # Mark this file as handled by adding its name.
        # A non-directory implicitly tombstones any entries with
        # a matching (or child) name.
        fs[name] = tombstone or not member.isdir()
        if not tombstone:
          if member.isfile():
            tar.addfile(member, fileobj=layer_tar.extractfile(member.name))
          else:
            tar.addfile(member, fileobj=None)
