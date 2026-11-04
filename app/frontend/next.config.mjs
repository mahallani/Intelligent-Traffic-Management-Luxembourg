/** Static export: `npm run build` writes ./out, served by the Python backend (app/backend/server.py). */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};
export default nextConfig;
