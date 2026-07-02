# psycopg2 Lambda layer (Docker-free)

This layer supplies `psycopg2` to the backend Lambda so `cdk synth` never needs
Docker bundling.

Populate it once before deploying (synth works even while empty):

```bash
cd examples/hybrid-webapp-demo/cdk/layers/psycopg2
pip install \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --target python \
  psycopg2-binary
```

The resulting `python/` directory is what the layer zips. It is intentionally
kept out of version control except for this README and the `.gitkeep`.
