"""This package pushes images to a Docker Registry."""



import argparse

from containerregistry.client import docker_creds
from containerregistry.client import docker_name
from containerregistry.client.v2_2 import docker_image as v2_2_image
from containerregistry.client.v2_2 import docker_session
from containerregistry.transport import transport_pool

import httplib2


parser = argparse.ArgumentParser(
    description='Push images to a Docker Registry.')

parser.add_argument('--name', action='store',
                    help=('The name of the docker image to push.'))

parser.add_argument('--tarball', action='store',
                    help='Where to load the image tarball.')

_THREADS = 8


def main():
  args = parser.parse_args()

  transport = transport_pool.Http(httplib2.Http, size=_THREADS)

  # This library can support push-by-digest, but the likelihood of a user
  # correctly providing us with the digest without using this library
  # directly is essentially nil.
  name = docker_name.Tag(args.name)

  # Resolve the appropriate credential to use based on the standard Docker
  # client logic.
  creds = docker_creds.DefaultKeychain.Resolve(name)

  with docker_session.Push(name, creds, transport, threads=_THREADS) as session:
    with v2_2_image.FromTarball(args.tarball) as v2_2_img:
      session.upload(v2_2_img)


if __name__ == '__main__':
  main()
