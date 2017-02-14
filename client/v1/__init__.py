import sys
x=sys.modules['containerregistry.client.v1']
  

from containerregistry.client.v1 import docker_http_
setattr(x, 'docker_http', docker_http_)


from containerregistry.client.v1 import docker_image_
setattr(x, 'docker_image', docker_image_)


from containerregistry.client.v1 import docker_session_
setattr(x, 'docker_session', docker_session_)


