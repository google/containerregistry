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

"""This package provides compatibility interfaces for OCI."""



import json

from containerregistry.client.v2_2 import docker_http
from containerregistry.client.v2_2 import docker_image



class OCIFromV22(docker_image.Delegate):
  """This compatibility interface serves an OCI image from a v2_2 image."""

  def __init__(self, image):
    """Constructor.

    Args:
      image: a DockerImage on which __enter__ has already been called.
    """
    super(OCIFromV22, self).__init__(image)

  def manifest(self):
    """Override."""
    manifest = json.loads(self._image.manifest())

    manifest['mediaType'] = docker_http.OCI_MANIFEST_MIME
    manifest['config']['mediaType'] = docker_http.OCI_CONFIG_JSON_MIME
    for layer in manifest['layers']:
      layer['mediaType'] = docker_http.OCI_LAYER_MIME

    return json.dumps(manifest, sort_keys=True)

  def media_type(self):
    """Override."""
    return docker_http.OCI_MANIFEST_MIME

  def __enter__(self):
    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    """Override."""
    pass


class V22FromOCI(docker_image.Delegate):
  """This compatibility interface serves a v2_2 image from an OCI image."""

  def __init__(self, image):
    """Constructor.

    Args:
      image: a DockerImage on which __enter__ has already been called.
    """
    super(V22FromOCI, self).__init__(image)

  def manifest(self):
    """Override."""
    manifest = json.loads(self._image.manifest())

    manifest['mediaType'] = docker_http.MANIFEST_SCHEMA2_MIME
    manifest['config']['mediaType'] = docker_http.CONFIG_JSON_MIME
    for layer in manifest['layers']:
      layer['mediaType'] = docker_http.LAYER_MIME

    return json.dumps(manifest, sort_keys=True)

  def media_type(self):
    """Override."""
    return docker_http.MANIFEST_SCHEMA2_MIME

  def __enter__(self):
    return self

  def __exit__(self, unused_type, unused_value, unused_traceback):
    """Override."""
    pass
