FROM node:22-bookworm-slim AS frontend
WORKDIR /source
RUN npm install -g pnpm@10.6.2
COPY src/GZCTF/ClientApp/ ./
RUN pnpm install --frozen-lockfile && pnpm exec tsc && pnpm exec vite build --configLoader runner

FROM mcr.microsoft.com/dotnet/sdk:9.0 AS backend
WORKDIR /source
COPY src/ ./src/
RUN dotnet publish src/GZCTF/GZCTF.csproj -c Release -o /publish -p:SkipFrontendBuild=true -p:EFOptimizeContext=false

FROM mcr.microsoft.com/dotnet/aspnet:9.0-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends libpcap0.8 libgdiplus ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=backend /publish/ ./
COPY --from=frontend /source/build/ ./wwwroot/
EXPOSE 8080
ENTRYPOINT ["dotnet", "GZCTF.dll"]
