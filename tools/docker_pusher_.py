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
"""This package pushes images to a Docker Registry."""



import argparse

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import docker_session
from containerregistry.tools import patched
from containerregistry.transport import transport_pool

import httplib2


parser = argparse.ArgumentParser(
    description='Push images to a Docker Registry.')

parser.add_argument('--name', action='store',
                    help=('The name of the docker image to push.'))

parser.add_argument('--tarball', action='store',
                    help='Where to load the image tarball.')

parser.add_argument('--stamp-info-file', action='append', required=False,
                    help=('A list of files from which to read substitutions '
                          'to make in the provided --name, e.g. {BUILD_USER}'))

_THREADS = 8


def Tag(name, files):
  """Perform substitutions in the provided tag name."""
  format_args = {}
  for infofile in files or []:
    with open(infofile) as info:
      for line in info:
        line = line.strip('\n')
        key, value = line.split(' ', 1)
        if key in format_args:
          print ('WARNING: Duplicate value for key "%s": '
                 'using "%s"' % (key, value))
        format_args[key] = value

  formatted_name = name.format(**format_args)

  return docker_name.Tag(formatted_name)


def main():
  args = parser.parse_args()

  if not args.name or not args.tarball:
    raise Exception('--name and --tarball are required arguments.')

  transport = transport_pool.Http(httplib2.Http, size=_THREADS)

  # This library can support push-by-digest, but the likelihood of a user
  # correctly providing us with the digest without using this library
  # directly is essentially nil.
  name = Tag(args.name, args.stamp_info_file)

  # Resolve the appropriate credential to use based on the standard Docker
  # client logic.
  creds = docker_creds.DefaultKeychain.Resolve(name)

  with docker_session.Push(name, creds, transport, threads=_THREADS) as session:
    with v2_2_image.FromTarball(args.tarball) as v2_2_img:
      session.upload(v2_2_img)


if __name__ == '__main__':
  with patched.Httplib2():
    main()
