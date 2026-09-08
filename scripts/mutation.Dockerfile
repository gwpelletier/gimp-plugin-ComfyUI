# Mutation-testing image: mutmut requires a Linux runtime (boxed/mutmut#397).
FROM python:3.12-slim

RUN pip install --no-cache-dir "pytest>=8" "pytest-cov>=5" "mutmut>=3"

WORKDIR /app
ENTRYPOINT ["mutmut"]
CMD ["run"]
