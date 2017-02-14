import sys
x=sys.modules['containerregistry.client.v2_2']
  

from containerregistry.client.v2_2 import docker_http_
setattr(x, 'docker_http', docker_http_)


from containerregistry.client.v2_2 import docker_image_
setattr(x, 'docker_image', docker_image_)


from containerregistry.client.v2_2 import v2_compat_
setattr(x, 'v2_compat', v2_compat_)


from containerregistry.client.v2_2 import util_
setattr(x, 'util', util_)


from containerregistry.client.v2_2 import docker_session_
setattr(x, 'docker_session', docker_session_)


