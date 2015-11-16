import json

class JSONDict(dict):
    def __init__(self, filename, **kwargs):
        super().__init__(**kwargs)
        self._filename = filename
        self.load_dict()

    def __setitem__(self, item, val):
        super().__setitem__(item, val)
        self.save_dict()

    def save_dict(self):
        with open(self._filename, "w") as f:
            data = json.dumps(dict(self.items()))
            f.write(data)

    def load_dict(self):
        try:
            with open(self._filename) as f:
                data = json.load(f)
                for k, v in data.items():
                    super().__setitem__(k, v)
        except FileNotFoundError:
            pass