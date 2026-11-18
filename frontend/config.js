/* PathSnap frontend configuration.

Resolution order for the backend URL:
  1. ?api=<url> query parameter  (e.g. ?api=http://192.168.1.10:8000)
  2. localStorage "pathsnap_api_base" (persisted from a previous ?api=)
  3. window.PATHSNAP_API_BASE set below
  4. same origin (when the backend serves this frontend)

For the two-laptop demo on Laptop 2, either open
  http://<laptop1-ip>:8000/?api=http://<laptop1-ip>:8000
or serve this folder statically and pass ?api= accordingly.
*/
window.PATHSNAP_API_BASE = window.PATHSNAP_API_BASE || "";
