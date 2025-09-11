class Counter:
    def __init__(self):
        self.inside = 0
        self.entered = 0
        self.exited = 0
        self.track_memory = {}

    def update(self, tracks):
        """
        tracks: lista de dicts con {"id": int, "x": int, "y": int}
        """
        for person in tracks:
            pid = person["id"]
            y = person["y"]

            if pid not in self.track_memory:
                self.track_memory[pid] = y
                continue

            prev_y = self.track_memory[pid]

            # línea virtual y=250 (ejemplo)
            if prev_y < 250 and y >= 250:
                self.entered += 1
                self.inside += 1
            elif prev_y >= 250 and y < 250:
                self.exited += 1
                self.inside = max(0, self.inside - 1)

            self.track_memory[pid] = y

        return {
            "inside": self.inside,
            "entered": self.entered,
            "exited": self.exited,
        }