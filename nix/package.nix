# nix/package.nix
#
# Nix derivation for the globaltalk Python package.
#
# Usage from flake.nix:
#   globaltalk = final.callPackage ./nix/package.nix { };
{
  lib,
  python3,
  buildPythonPackage ? python3.pkgs.buildPythonPackage,
  hatchling ? python3.pkgs.hatchling,
}:

buildPythonPackage {
  pname = "globaltalk";
  version = "0.1.0";

  # Build backend
  pyproject = true;

  src = lib.cleanSource ../.;

  build-system = [
    hatchling
  ];

  # No runtime dependencies — the package uses only the Python standard library.
  dependencies = [ ];

  # Basic smoke-test: make sure the entry-point loads and prints help without
  # requiring netatalk to be present on the build host.
  checkPhase = ''
    echo "==> globaltalk --help"
    $out/bin/globaltalk --help

    echo "==> globaltalk scrape --help"
    $out/bin/globaltalk scrape --help

    echo "==> globaltalk metrics --help"
    $out/bin/globaltalk metrics --help

    echo "==> globaltalk nodelist --help"
    $out/bin/globaltalk nodelist --help
  '';

  meta = {
    description = "Tools for the GlobalTalk community AppleTalk network";
    longDescription = ''
      A unified toolkit for the GlobalTalk network — a large, community-operated
      AppleTalk network connecting retro Apple computers and modern applications.

      Provides three commands via a single `globaltalk` entry-point:

        globaltalk scrape    - Scrape the network using netatalk's getzones/nbplkup
                               and emit a JSON snapshot.
        globaltalk metrics   - Convert a JSON snapshot into Prometheus metrics for
                               use with node_exporter's textfile collector.
        globaltalk nodelist  - Convert a list of hostnames/IPs into a jrouter-
                               compatible YAML peer configuration.
    '';
    homepage = "https://github.com/nikdoof/globaltalk-scraper";
    license = lib.licenses.mit;
    maintainers = [ ];
    mainProgram = "globaltalk";
    # netatalk (getzones/nbplkup) is a runtime requirement of `globaltalk scrape`
    # but it is not a Python dependency and is intentionally left out of the Nix
    # closure — it must be present in the system environment at runtime.
    platforms = lib.platforms.unix;
  };
}
