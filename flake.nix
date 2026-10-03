{
  description = "Umbod development tools";

  # This release supplies Python 3.14 and Helm 3, as required by Umbod.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
    in {
      devShells = nixpkgs.lib.genAttrs systems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShell {
            packages = with pkgs; [
              bashInteractive
              git
              curl
              python314
              uv
              bun
              nodejs_22
              (docker_29.override { clientOnly = true; })
              docker-compose
              kubernetes-helm
              kind
              kubectl
              kubeconform
            ];

            # Keep uv on the pinned interpreter; dependencies remain in uv.lock.
            UV_PYTHON = "${pkgs.python314}/bin/python3.14";
            UV_PYTHON_DOWNLOADS = "never";
          };
        });
    };
}
