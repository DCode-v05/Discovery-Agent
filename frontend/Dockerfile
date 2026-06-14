FROM node:20-alpine

WORKDIR /app

COPY frontend/package.json ./
RUN npm install --no-audit --no-fund

COPY frontend ./

# The browser calls the backend directly; CORS is open on the backend.
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

EXPOSE 5173
CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
