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

"""This package provides compatibility interfaces for v1/v2."""



import cStringIO
import gzip
import hashlib
import json

from containerregistry.client.v2 import docker_image as v2_image
from containerregistry.client.v2 import util as v2_util
from containerregistry.client.v2_2 import docker_http
from containerregistry.client.v2_2 import docker_image as v2_2_image



class BadDigestException(Exception):
  """Exceptions when a bad digest is supplied."""


EMPTY_TAR_DIGEST = (
    'sha256:a3ed95caeb02ffe68cdd9fd84406680ae93d633cb16422d00e8a7c22955b46d4')


class V22FromV2(v2_2_image.DockerImage):
  """This compatibility interface serves the v2 interface from a v2_2 image."""

  def __init__(self, v2_img):
    """Constructor.

    Args:
      v2_img: a v2 DockerImage on which __enter__ has already been called.

    Raises:
      ValueError: an incorrectly typed argument was supplied.
    """
    self._v2_image = v2_img
    self._ProcessImage()

  def _ProcessImage(self):
    """Constructs schema 2 manifest from schema 1 manifest."""
    raw_manifest_schema1 = self._v2_image.manifest()
    manifest_schema1 = json.loads(raw_manifest_schema1)

    histories = []
    diff_ids = []
    layers = []
    for digest in reversed(self._v2_image.fs_layers()):
      diff_id, size = self._GetDiffIdAndSize(digest)
      layers += [{'mediaType': docker_http.LAYER_MIME,
                  'size': size,
                  'digest': digest}]
      diff_ids += [diff_id]

    rootfs = {'diff_ids': diff_ids, 'type': 'layers'}

    for history in reversed(manifest_schema1.get('history')):
      v1_compatibility = json.loads(history.get('v1Compatibility'))
      # created_by in history is the cmd which was run to create the layer.
      # Cmd in container config may be empty array.
      history = {}
      if 'container_config' in v1_compatibility:
        container_config = v1_compatibility.get('container_config')
        if container_config.get('Cmd'):
          history['created_by'] = container_config['Cmd'][0]

      if 'created' in v1_compatibility:
        history['created'] = v1_compatibility.get('created')

      histories += [history]

    v1_compatibility = json.loads(
        manifest_schema1.get('history', [''])[0].get('v1Compatibility', {}))

    config = {
        'architecture': v1_compatibility.get('architecture', ''),
        'config': v1_compatibility.get('config', {}),
        'container': v1_compatibility.get('container', ''),
        'container_config': v1_compatibility.get('container_config', {}),
        'docker_version': v1_compatibility.get('docker_version', ''),
        'history': histories,
        'os': v1_compatibility.get('os', ''),
        'rootfs': rootfs
    }

    if 'created' in v1_compatibility:
      config['created'] = v1_compatibility.get('created')

    self._config_file = json.dumps(config, sort_keys=True)
    config_descriptor = {
        'mediaType': docker_http.CONFIG_JSON_MIME,
        'size': len(self._config_file),
        'digest': 'sha256:' + hashlib.sha256(self._config_file).hexdigest()
    }

    manifest_schema2 = {
        'schemaVersion': 2,
        'mediaType': docker_http.MANIFEST_SCHEMA2_MIME,
        'config': config_descriptor,
        'layers': layers
    }
    self._manifest = json.dumps(manifest_schema2, sort_keys=True)

  def _GetDiffIdAndSize(
      self,
      digest
  ):
    """Unzip the layer blob file and sha256."""
    buff = self._v2_image.blob(digest)
    compressed_file = cStringIO.StringIO(buff)
    decompressed_file = gzip.GzipFile(fileobj=compressed_file, mode='rb')
    return ('sha256:' + hashlib.sha256(decompressed_file.read()).hexdigest(),
            len(buff))

  def manifest(self):
    """Override."""
    return self._manifest

  def config_file(self):
    """Override."""
    return self._config_file

  def blob(self, digest):
    """Override."""
    return self._v2_image.blob(digest)

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass


class V2FromV22(v2_image.DockerImage):
  """This compatibility interface serves the v2 interface from a v2_2 image."""

  def __init__(self, v2_2_img):
    """Constructor.

    Args:
      v2_2_img: a v2_2 DockerImage on which __enter__ has already been called.

    Raises:
      ValueError: an incorrectly typed argument was supplied.
    """
    self._v2_2_image = v2_2_img
    self._ProcessImage()

  def _ProcessImage(self):
    """Constructs schema 1 manifest from schema 2 manifest and config file."""
    manifest_schema2 = json.loads(self._v2_2_image.manifest())
    raw_config = self._v2_2_image.config_file()
    config = json.loads(raw_config)

    parent = ''

    histories = config.get('history', {})
    layer_count = len(histories)
    v2_layer_index = 0
    layers = manifest_schema2.get('layers', {})

    # from base to top
    fs_layers = []
    v1_histories = []
    for v1_layer_index, history in enumerate(histories):
      digest, v2_layer_index = self._GetSchema1LayerDigest(
          history, layers, v1_layer_index, v2_layer_index)

      if v1_layer_index != layer_count - 1:
        layer_id = self._GenerateV1LayerId(digest, parent)
        v1_compatibility = self._BuildV1Compatibility(layer_id, parent, history)
      else:
        layer_id = self._GenerateV1LayerId(digest, parent, raw_config)
        v1_compatibility = self._BuildV1CompatibilityForTopLayer(
            layer_id, parent, history, config)
      parent = layer_id
      fs_layers = [{'blobSum': digest}] + fs_layers
      v1_histories = [{'v1Compatibility': v1_compatibility}] + v1_histories

    manifest_schema1 = {
        'schemaVersion': 1,
        'name': 'unused',
        'tag': 'unused',
        'architecture': config.get('architecture', ''),
        'fsLayers': fs_layers,
        'history': v1_histories
    }
    self._manifest = v2_util.Sign(json.dumps(manifest_schema1, sort_keys=True))

  def _GenerateV1LayerId(
      self,
      digest,
      parent,
      raw_config=None
  ):
    parts = digest.rsplit(':', 1)
    if len(parts) != 2:
      raise BadDigestException('Invalid Digest: %s, must be in '
                               'algorithm : blobSumHex format.' % (digest))

    data = str(parts[1] + ' ' + parent)

    if raw_config:
      data += ' ' + str(raw_config)
    return hashlib.sha256(data).hexdigest()

  def _BuildV1Compatibility(
      self,
      layer_id,
      parent,
      history
  ):
    v1_compatibility = {
        'id': layer_id,
        'parent': parent,
        'container_config': {
            'Cmd': [history['created_by']]
        } if 'created_by' in history else {},
        'throwaway': True if 'empty_layer' in history else False
    }

    if 'created' in history:
      v1_compatibility['created'] = history.get('created')

    if 'comment' in history:
      v1_compatibility['comment'] = history.get('comment')

    if 'author' in history:
      v1_compatibility['author'] = history.get('author')

    return json.dumps(v1_compatibility, sort_keys=True)

  def _BuildV1CompatibilityForTopLayer(
      self,
      layer_id,
      parent,
      history,
      config
  ):
    v1_compatibility = {
        'architecture': config.get('architecture', ''),
        'container': config.get('container', ''),
        'docker_version': config.get('docker_version', ''),
        'os': config.get('os', ''),
        'config': config.get('config', {}),
        'container_config': config.get('container_config', {}),
        'id': layer_id,
        'parent': parent,
        'throwaway': True if 'empty_layer' in history else False
    }

    if 'created' in config:
      v1_compatibility['created'] = config.get('created')

    return json.dumps(v1_compatibility, sort_keys=True)

  def _GetSchema1LayerDigest(
      self,
      history,
      layers,
      v1_layer_index,
      v2_layer_index
  ):
    if 'empty_layer' in history:
      return (EMPTY_TAR_DIGEST, v2_layer_index)
    else:
      return (layers[v2_layer_index]['digest'], v2_layer_index + 1)

  def manifest(self):
    """Override."""
    return self._manifest

  def blob(self, digest):
    """Override."""
    return self._v2_2_image.blob(digest)

  # __enter__ and __exit__ allow use as a context manager.
  def __enter__(self):
    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    pass
