FROM mcr.microsoft.com/dotnet/sdk:10.0-preview

# GitHub Actions runner
ARG RUNNER_VERSION=2.331.0
RUN mkdir -p /opt/runner \
    && curl -fsSL https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz \
    | tar xz -C /opt/runner

# Build dependencies (nodejs/npm required for CodeQL and JS-based GitHub Actions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git jq unzip nodejs npm python3 \
    && rm -rf /var/lib/apt/lists/*

# Trufflehog CLI (secret scanning — replaces Docker action)
ARG TRUFFLEHOG_VERSION=3.88.1
RUN curl -sSfL \
      "https://github.com/trufflesecurity/trufflehog/releases/download/v${TRUFFLEHOG_VERSION}/trufflehog_${TRUFFLEHOG_VERSION}_linux_amd64.tar.gz" \
      -o /tmp/trufflehog.tar.gz \
    && tar -xzf /tmp/trufflehog.tar.gz -C /usr/local/bin trufflehog \
    && rm /tmp/trufflehog.tar.gz

# Run as non-root user — also grant write access to /usr/share/dotnet so
# actions/setup-dotnet can install additional SDK versions.
RUN useradd -m runner \
    && chown -R runner:runner /opt/runner \
    && chown -R runner:runner /usr/share/dotnet
USER runner

# Stryker.NET (mutation testing) — installed as runner user
RUN dotnet tool install -g dotnet-stryker
WORKDIR /opt/runner
COPY --chown=runner:runner startup.sh ./startup.sh
ENTRYPOINT ["./startup.sh"]
