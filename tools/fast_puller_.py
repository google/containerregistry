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
"""This package pulls images from a Docker Registry.

Unlike docker_puller the format this uses is proprietary.
"""



import argparse

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2 import docker_image as v2_image
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import save
from containerregistry.client.v2_2 import v2_compat
from containerregistry.tools import patched
from containerregistry.transport import transport_pool

import httplib2


parser = argparse.ArgumentParser(
    description='Pull images from a Docker Registry, faaaaast.')

parser.add_argument('--name', action='store',
                    help=('The name of the docker image to pull and save. '
                          'Supports fully-qualified tag or digest references.'))

parser.add_argument('--directory', action='store',
                    help='Where to save the image\'s files.')

_THREADS = 8


def main():
  args = parser.parse_args()

  if not args.name or not args.directory:
    raise Exception('--name and --directory are required arguments.')

  transport = transport_pool.Http(httplib2.Http, size=_THREADS)

  if '@' in args.name:
    name = docker_name.Digest(args.name)
  else:
    name = docker_name.Tag(args.name)

  # Resolve the appropriate credential to use based on the standard Docker
  # client logic.
  creds = docker_creds.DefaultKeychain.Resolve(name)

  with v2_2_image.FromRegistry(name, creds, transport) as v2_2_img:
    if v2_2_img.exists():
      save.fast(v2_2_img, args.directory, threads=_THREADS)
      return

  with v2_image.FromRegistry(name, creds, transport) as v2_img:
    with v2_compat.V22FromV2(v2_img) as v2_2_img:
      save.fast(v2_2_img, args.directory, threads=_THREADS)
      return


if __name__ == '__main__':
  with patched.Httplib2():
    main()
