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
"""This package pushes images to a Docker Registry.

The format this tool *expects* to deal with is (unlike docker_pusher)
proprietary, however, unlike {fast,docker}_puller the signature of this tool is
compatible with docker_pusher.
"""



import argparse

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import docker_session
from containerregistry.tools import patched
from containerregistry.transport import transport_pool

import httplib2


parser = argparse.ArgumentParser(
    description='Push images to a Docker Registry, faaaaaast.')

parser.add_argument('--name', action='store',
                    help=('The name of the docker image to push.'))

# The name of this flag was chosen for compatibility with docker_pusher.py
parser.add_argument('--tarball', action='store',
                    help='An optional legacy base image tarball.')

parser.add_argument('--config', action='store',
                    help='The path to the file storing the image config.')

parser.add_argument('--digest', action='append',
                    help='The list of layer digest filenames in order.')

parser.add_argument('--layer', action='append',
                    help='The list of layer filenames in order.')

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

  if not args.name:
    raise Exception('--name is a required arguments.')

  # This library can support push-by-digest, but the likelihood of a user
  # correctly providing us with the digest without using this library
  # directly is essentially nil.
  name = Tag(args.name, args.stamp_info_file)

  if not args.config and (args.layer or args.digest):
    raise Exception(
        'Using --layer or --digest requires --config to be specified.')

  if not args.config and not args.tarball:
    raise Exception('Either --config or --tarball must be specified.')

  # If config is specified, use that.  Otherwise, fallback on reading
  # the config from the tarball.
  config = args.config
  if args.config:
    with open(args.config, 'r') as reader:
      config = reader.read()
  elif args.tarball:
    with v2_2_image.FromTarball(args.tarball) as base:
      config = base.config_file()

  if len(args.digest or []) != len(args.layer or []):
    raise Exception('--digest and --layer must have matching lengths.')

  transport = transport_pool.Http(httplib2.Http, size=_THREADS)

  # Resolve the appropriate credential to use based on the standard Docker
  # client logic.
  creds = docker_creds.DefaultKeychain.Resolve(name)

  with docker_session.Push(name, creds, transport, threads=_THREADS) as session:
    with v2_2_image.FromDisk(config, zip(args.digest or [], args.layer or []),
                             legacy_base=args.tarball) as v2_2_img:
      session.upload(v2_2_img)


if __name__ == '__main__':
  with patched.Httplib2():
    main()
