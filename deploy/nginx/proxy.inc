set $assistant_upstream http://assistant:8000;
proxy_pass $assistant_upstream;
proxy_http_version 1.1;
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Connection "";
# The application does not need the gateway's demonstration-account credentials.
proxy_set_header Authorization "";
proxy_connect_timeout 5s;
proxy_read_timeout 180s;
proxy_send_timeout 30s;
proxy_next_upstream off;
