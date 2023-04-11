import subprocess
import json

class Remarkable:
    def __init__(self):
        import rmapy.const
        rmapy.const.AUTH_BASE_URL = "https://webapp-prod.cloud.remarkable.engineering"
        rmapy.const.BASE_URL = "https://internal.cloud.remarkable.com"
        rmapy.const.DEVICE_TOKEN_URL = rmapy.const.AUTH_BASE_URL + "/token/json/2/device/new"
        rmapy.const.USER_TOKEN_URL = rmapy.const.AUTH_BASE_URL + "/token/json/2/user/new"

        from rmapy.api import Client
        self.shim = Client()

        self.check_rmapi_binary()
    
    def auth_if_needed(self, token):
        if not self.is_auth():
            print("Not authenticated")
            if token:
                print("Using register-device-token: '%s'" % token)
                self.register_device(token)
                self.renew_token()
                if self.is_auth():
                    print("Success!")
                    return True
                else:
                    print("Error -- still not authenticated")
                    exit(1)
            else:
                print("Please authenticate with --register-device-token")
                print("Receive a token at https://my.remarkable.com/device/desktop/connect")
                exit(1)
        return True

    def is_auth(self):
        return self.shim.is_auth()

    def register_device(self, token):
        return self.shim.register_device(token)
    
    def renew_token(self):
        return self.shim.renew_token()
    
    def check_rmapi_binary(self):
        out = subprocess.run(["rmapi", "version"], capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"Couldn't find rmapi binary: exit code {out.returncode}: {out.stdout} {out.stderr}")

    def ls(self, folder, ftype='[f]'):
        out = subprocess.run(["rmapi", "-ni", "ls", folder], capture_output=True)
        if out.returncode != 0 and "directory doesn't exist" in str(out.stderr):
            raise FileNotFoundError(f"{out.stderr}")
        elif out.returncode != 0:
            raise RuntimeError(f"Couldn't run ls: exit code {out.returncode}: {out.stdout} {out.stderr}")

        files = out.stdout.decode().splitlines()
        files = list(map(lambda x: x.split('\t'), files))
        files = list(filter(lambda x: x[0] == ftype, files))
        files = list(map(lambda x: x[1], files))

        return files

    def mkdir(self, folder):
        mk = subprocess.run(["rmapi", "mkdir", folder], capture_output=True)
        if mk.returncode != 0:
            raise RuntimeError(f"Couldn't create directory: exit code {mk.returncode}: {mk.stdout} {mk.stderr}")
        return True

    def put(self, local_path, remote_folder):
        write = subprocess.run(["rmapi", "-ni", "put", local_path, remote_folder], capture_output=True)
        if write.returncode != 0:
            raise RuntimeError(f"Couldn't write file: exit code {write.returncode}: {write.stdout} {write.stderr}")
        return True

    def stat(self, remote_path):
        out = subprocess.run(["rmapi", "-ni", "stat", remote_path], capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"Couldn't stat file: exit code {out.returncode}: {out.stdout} {out.stderr}")
        return json.loads(out.stdout)

    def rm(self, remote_path):
        out = subprocess.run(["rmapi", "-ni", "rm", remote_path], capture_output=True)
        if out.returncode != 0:
            raise RuntimeError(f"Couldn't rm file: exit code {out.returncode}: {out.stdout} {out.stderr}")
        return True


