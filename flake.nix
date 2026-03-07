{
  description = "GlobalTalk toolkit - tools for the GlobalTalk community AppleTalk network";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    let
      # Package derivation, factored out so the NixOS module can reference it
      # without duplicating it per-system.
      overlay = final: prev: {
        globaltalk = final.callPackage ./nix/package.nix { };
      };

      # NixOS module (system-independent).
      nixosModule =
        {
          config,
          lib,
          pkgs,
          ...
        }:
        let
          cfg = config.services.globaltalk;
          globaltalkPkg = pkgs.globaltalk;
        in
        {
          options.services.globaltalk = {
            scrape = {
              enable = lib.mkEnableOption "GlobalTalk network scraper timer";

              interval = lib.mkOption {
                type = lib.types.str;
                default = "5m";
                description = ''
                  How often to run the scraper. Accepts systemd calendar
                  expressions (e.g. "5m", "hourly", "*:0/15").
                '';
              };

              outputFile = lib.mkOption {
                type = lib.types.str;
                default = "/var/lib/globaltalk/scrape.json";
                description = "Path to write the JSON snapshot to.";
              };

              workers = lib.mkOption {
                type = lib.types.int;
                default = 10;
                description = "Number of concurrent zone-scan threads.";
              };

              zones = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ ];
                description = ''
                  Restrict scanning to these zone names. Leave empty to scan
                  all discovered zones.
                '';
              };

              extraArgs = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ ];
                description = "Additional arguments passed to `globaltalk scrape`.";
              };
            };

            metrics = {
              enable = lib.mkEnableOption "GlobalTalk Prometheus metrics exporter";

              inputFile = lib.mkOption {
                type = lib.types.str;
                default = config.services.globaltalk.scrape.outputFile;
                description = ''
                  Path to the JSON snapshot produced by the scraper.
                  Defaults to the scrape output file.
                '';
              };

              outputFile = lib.mkOption {
                type = lib.types.str;
                default = "/var/lib/prometheus/node-exporter/globaltalk.prom";
                description = ''
                  Path to write the Prometheus .prom file for node_exporter's
                  textfile collector.
                '';
              };

              prefix = lib.mkOption {
                type = lib.types.str;
                default = "globaltalk";
                description = "Metric name prefix.";
              };

              extraArgs = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ ];
                description = "Additional arguments passed to `globaltalk metrics`.";
              };
            };
          };

          config = lib.mkMerge [
            # ----------------------------------------------------------------
            # Scraper service + timer
            # ----------------------------------------------------------------
            (lib.mkIf cfg.scrape.enable {
              systemd.services.globaltalk-scrape = {
                description = "GlobalTalk network scraper";
                after = [ "network.target" ];
                serviceConfig = {
                  Type = "oneshot";
                  ExecStartPre = "/run/current-system/sw/bin/mkdir -p ${builtins.dirOf cfg.scrape.outputFile}";
                  ExecStart =
                    let
                      zoneArgs = lib.concatMap (z: [
                        "--zone"
                        z
                      ]) cfg.scrape.zones;
                      args = lib.escapeShellArgs (
                        [
                          "--output"
                          cfg.scrape.outputFile
                          "--workers"
                          (toString cfg.scrape.workers)
                        ]
                        ++ zoneArgs
                        ++ cfg.scrape.extraArgs
                      );
                    in
                    "${globaltalkPkg}/bin/globaltalk scrape ${args}";
                  # Scraper needs access to netatalk sockets / network tools.
                  PrivateTmp = false;
                };
              };

              systemd.timers.globaltalk-scrape = {
                description = "Run GlobalTalk scraper periodically";
                wantedBy = [ "timers.target" ];
                timerConfig = {
                  OnBootSec = "1m";
                  OnUnitActiveSec = cfg.scrape.interval;
                  Unit = "globaltalk-scrape.service";
                };
              };
            })

            # ----------------------------------------------------------------
            # Metrics service (runs after each scrape)
            # ----------------------------------------------------------------
            (lib.mkIf cfg.metrics.enable {
              systemd.services.globaltalk-metrics = {
                description = "GlobalTalk Prometheus metrics generator";
                after = lib.optional cfg.scrape.enable "globaltalk-scrape.service";
                serviceConfig = {
                  Type = "oneshot";
                  ExecStartPre = "/run/current-system/sw/bin/mkdir -p ${builtins.dirOf cfg.metrics.outputFile}";
                  ExecStart =
                    let
                      args = lib.escapeShellArgs (
                        [
                          cfg.metrics.inputFile
                          "--output"
                          cfg.metrics.outputFile
                          "--prefix"
                          cfg.metrics.prefix
                        ]
                        ++ cfg.metrics.extraArgs
                      );
                    in
                    "${globaltalkPkg}/bin/globaltalk metrics ${args}";
                };
              };

              # If the scraper is also enabled, chain metrics generation onto
              # the scrape timer so it always runs right after a fresh snapshot.
              systemd.services.globaltalk-scrape = lib.mkIf cfg.scrape.enable {
                serviceConfig.ExecStartPost = "${config.systemd.services.globaltalk-metrics.serviceConfig.ExecStart
                }";
              };
            })
          ];
        };

    in
    # Per-system outputs (packages, apps, devShells).
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs {
          inherit system;
          overlays = [ overlay ];
        };
      in
      {
        # ── packages ──────────────────────────────────────────────────────
        packages = {
          globaltalk = pkgs.globaltalk;
          default = pkgs.globaltalk;
        };

        # ── runnable app (nix run .#globaltalk) ───────────────────────────
        apps = {
          globaltalk = {
            type = "app";
            program = "${pkgs.globaltalk}/bin/globaltalk";
          };
          default = self.apps.${system}.globaltalk;
        };

        # ── development shell ──────────────────────────────────────────────
        devShells.default = pkgs.mkShell {
          packages = [
            (pkgs.python3.withPackages (ps: [ ]))
            pkgs.uv
            pkgs.ruff
          ];
          shellHook = ''
            echo "GlobalTalk development shell"
            echo "Run 'uv sync' to set up the project environment."
          '';
        };
      }
    )

    # System-independent outputs (overlay + NixOS module).
    // {
      overlays.default = overlay;
      nixosModules.default = nixosModule;
      # Legacy alias used by some tooling.
      nixosModule = nixosModule;
    };
}
