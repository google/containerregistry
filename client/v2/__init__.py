import sys
x=sys.modules['containerregistry.client.v2']
  

from containerregistry.client.v2 import docker_http_
setattr(x, 'docker_http', docker_http_)


from containerregistry.client.v2 import docker_image_
setattr(x, 'docker_image', docker_image_)


from containerregistry.client.v2 import util_
setattr(x, 'util', util_)


from containerregistry.client.v2 import v1_compat_
setattr(x, 'v1_compat', v1_compat_)


from containerregistry.client.v2 import docker_session_
setattr(x, 'docker_session', docker_session_)


from containerregistry.client.v2 import append_
setattr(x, 'append', append_)


