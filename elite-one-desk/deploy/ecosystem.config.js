// PM2 alternative to the systemd unit. Use one or the other.
//
//   pm2 start deploy/ecosystem.config.js
//   pm2 save && pm2 startup
module.exports = {
  apps: [
    {
      name: "elite-one-desk",
      // `output: standalone` produces a server that needs no node_modules
      // beside it — which is what makes an atomic release swap safe.
      script: ".next/standalone/server.js",
      cwd: "/var/www/elite-one-desk/app",
      instances: 1,
      exec_mode: "fork",
      env: {
        NODE_ENV: "production",
        PORT: 3000,
        HOSTNAME: "127.0.0.1",
      },
      max_memory_restart: "512M",
      autorestart: true,
      kill_timeout: 10000,
      error_file: "/var/log/elite-one-desk/error.log",
      out_file: "/var/log/elite-one-desk/out.log",
      merge_logs: true,
      time: true,
    },
  ],
};
