SSRF 001 - Preview Fetch

Goal:
  Find the flag by abusing the server-side URL preview functionality.

What you are practicing:
  - Identifying SSRF in a preview/fetch feature
  - Thinking beyond localhost/127.0.0.1 blacklists
  - Accessing internal services on a Docker network

Hints (light):
  - The app fetches URLs from the server, not your browser.
  - "Localhost" is not the only internal address a container can reach.
  - Try service names that might exist on the same Docker network.
