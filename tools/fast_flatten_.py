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
"""This package flattens image metadata into a single tarball."""



import argparse
import tarfile

from containerregistry.client.v2_2 import docker_image as v2_2_image

parser = argparse.ArgumentParser(description='Flatten container images.')

# The name of this flag was chosen for compatibility with docker_pusher.py
parser.add_argument('--tarball', action='store',
                    help='An optional legacy base image tarball.')

parser.add_argument('--config', action='store',
                    help='The path to the file storing the image config.')

parser.add_argument('--digest', action='append',
                    help='The list of layer digest filenames in order.')

parser.add_argument('--layer', action='append',
                    help='The list of layer filenames in order.')

# Output arguments.
parser.add_argument('--filesystem', action='store',
                    help='The name of where to write the filesystem tarball.')

parser.add_argument('--metadata', action='store',
                    help=('The name of where to write the container '
                          'startup metadata.'))

_THREADS = 8


def main():
  args = parser.parse_args()

  if not args.config and (args.layer or args.digest):
    raise Exception(
        'Using --layer or --digest requires --config to be specified.')

  if not args.filesystem or not args.metadata:
    raise Exception(
        '--filesystem and --metadata are required flags.')

  if not args.config and not args.tarball:
    raise Exception('Either --config or --tarball must be specified.')

  # If config is specified, use that.  Otherwise, fall back on reading
  # the config from the tarball.
  if args.config:
    with open(args.config, 'r') as reader:
      config = reader.read()
  elif args.tarball:
    with v2_2_image.FromTarball(args.tarball) as base:
      config = base.config_file()
  else:
    config = args.config

  if len(args.digest or []) != len(args.layer or []):
    raise Exception('--digest and --layer must have matching lengths.')

  with v2_2_image.FromDisk(config, zip(args.digest or [], args.layer or []),
                           legacy_base=args.tarball) as v2_2_img:
    with tarfile.open(args.filesystem, 'w') as tar:
      v2_2_image.extract(v2_2_img, tar)

    with open(args.metadata, 'w') as f:
      f.write(v2_2_img.config_file())

if __name__ == '__main__':
  main()
