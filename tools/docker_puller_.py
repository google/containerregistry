"""This package anonymously pulls images from a Docker Registry.

TODO(user): support authenticated pulls.
"""



import argparse
import tarfile

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v1 import docker_image as v1_image
from containerregistry.client.v2 import docker_image as v2_image
from containerregistry.client.v2 import v1_compat
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import v2_compat
from containerregistry.transport import transport_pool

import httplib2

parser = argparse.ArgumentParser(
    description='Pull images from a Docker Registry.')

parser.add_argument('--name', action='store',
                    help='The name of the docker image to pull and save.')

parser.add_argument('--tarball', action='store',
                    help='Where to save the image tarball.')


def main():
  args = parser.parse_args()

  creds = docker_creds.Anonymous()
  transport = transport_pool.Http(httplib2.Http, size=8)

  name = docker_name.Tag(args.name)

  with tarfile.open(name=args.tarball, mode='w') as tar:
    with v2_2_image.FromRegistry(name, creds, transport) as v2_2_img:
      if v2_2_img.exists():
        with v2_compat.V2FromV22(v2_2_img) as v2_img:
          with v1_compat.V1FromV2(v2_img) as v1_img:
            v1_image.save(name, v1_img, tar)
            return

    with v2_image.FromRegistry(name, creds, transport) as v2_img:
      with v1_compat.V1FromV2(v2_img) as v1_img:
        v1_image.save(name, v1_img, tar)
        return


if __name__ == '__main__':
  main()
