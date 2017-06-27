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

"""This package provides tools for saving docker images."""



import cStringIO
import hashlib
import json
import os
import tarfile

import concurrent.futures
from containerregistry.client import docker_name
from containerregistry.client.v1 import docker_image as v1_image
from containerregistry.client.v1 import save as v1_save
from containerregistry.client.v2 import v1_compat
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import v2_compat



def _diff_id(v1_img, blob):
  unzipped = v1_img.uncompressed_layer(blob)
  return 'sha256:' + hashlib.sha256(unzipped).hexdigest()


def multi_image_tarball(
    tag_to_image,
    tar,
    tag_to_v1_image=None
):
  """Produce a "docker save" compatible tarball from the DockerImages.

  Args:
    tag_to_image: A dictionary of tags to the images they label.
    tar: the open tarfile into which we are writing the image tarball.
    tag_to_v1_image: A dictionary of tags to the the v1 form of the images
        they label.  If this isn't provided, the image is simply converted.
  """

  def add_file(filename, contents):
    info = tarfile.TarInfo(filename)
    info.size = len(contents)
    tar.addfile(tarinfo=info, fileobj=cStringIO.StringIO(contents))

  tag_to_v1_image = tag_to_v1_image or {}

  # The manifest.json file contains a list of the images to load
  # and how to tag them.  Each entry consists of three fields:
  #  - Config: the name of the image's config_file() within the
  #           saved tarball.
  #  - Layers: the list of filenames for the blobs constituting
  #           this image.  The order is the reverse of the v1
  #           ancestry ordering.
  #  - RepoTags: the list of tags to apply to this image once it
  #             is loaded.
  manifests = []

  for (tag, image) in tag_to_image.iteritems():
    # The config file is stored in a blob file named with its digest.
    digest = hashlib.sha256(image.config_file()).hexdigest()
    add_file(digest + '.json', image.config_file())

    cfg = json.loads(image.config_file())
    diffs = set(cfg.get('rootfs', {}).get('diff_ids', []))

    v1_img = tag_to_v1_image.get(tag)
    if not v1_img:
      v2_img = v2_compat.V2FromV22(image)
      v1_img = v1_compat.V1FromV2(v2_img)
      tag_to_v1_image[tag] = v1_img

    # Add the manifests entry for this image.
    manifests.append({
        'Config': digest + '.json',
        'Layers': [
            layer_id + '/layer.tar'
            # We don't just exclude the empty tar because we leave its diff_id
            # in the set when coming through v2_compat.V22FromV2
            for layer_id in reversed(v1_img.ancestry(v1_img.top()))
            if _diff_id(v1_img, layer_id) in diffs
        ],
        'RepoTags': [str(tag)]
    })

  # v2.2 tarballs are a superset of v1 tarballs, so delegate
  # to v1 to save itself.
  v1_save.multi_image_tarball(tag_to_v1_image, tar)

  add_file('manifest.json', json.dumps(manifests, sort_keys=True))


def tarball(
    name,
    image,
    tar
):
  """Produce a "docker save" compatible tarball from the DockerImage.

  Args:
    name: The tag name to write into repositories and manifest.json
    image: a docker image to save.
    tar: the open tarfile into which we are writing the image tarball.
  """
  multi_image_tarball({name: image}, tar, {})


def fast(
    image,
    directory,
    threads=1
):
  """Produce a FromDisk compatible file layout under the provided directory.

  After calling this, the following filesystem will exist:
    directory/
      config.json  <-- only *.json, the image's config
      001.tar.gz   <-- the first layer's .tar.gz filesystem delta
      001.sha256   <-- the sha256 of 1.tar.gz with a "sha256:" prefix.
      ...
      N.tar.gz     <-- the Nth layer's .tar.gz filesystem delta
      N.sha256     <-- the sha256 of N.tar.gz with a "sha256:" prefix.

  We pad layer indices to only 3 digits because of a known ceiling on the number
  of filesystem layers Docker supports.

  Args:
    image: a docker image to save.
    directory: an existing empty directory under which to save the layout.
    threads: the number of threads to use when performing the upload.

  Returns:
    A tuple whose first element is the path to the config file, and whose second
    element is an ordered list of tuples whose elements are the filenames
    containing: (.sha256, .tar.gz) respectively.
  """

  def write_file(
      name,
      accessor,
      arg
  ):
    with open(name, 'wb') as f:
      f.write(accessor(arg))

  with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
    future_to_params = {}
    config_file = os.path.join(directory, 'config.json')
    f = executor.submit(write_file, config_file,
                        lambda unused: image.config_file(), 'unused')
    future_to_params[f] = config_file

    idx = 0
    layers = []
    for blob in reversed(image.fs_layers()):
      # Create a local copy
      digest_name = os.path.join(directory, '%03d.sha256' % idx)
      f = executor.submit(write_file, digest_name,
                          # Strip the sha256: prefix
                          lambda blob: blob[7:], blob)
      future_to_params[f] = digest_name

      layer_name = os.path.join(directory, '%03d.tar.gz' % idx)
      f = executor.submit(write_file, layer_name, image.blob, blob)
      future_to_params[f] = layer_name

      layers.append((digest_name, layer_name))
      idx += 1

    # Wait for completion.
    for future in concurrent.futures.as_completed(future_to_params):
      future.result()

  return (config_file, layers)
