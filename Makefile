# Root của uv workspace — một lệnh cho cả bốn package. Target riêng của từng package (demo, run, login...)
# vẫn nằm trong Makefile của thư mục đó; `make -C gateway login` hoặc `cd gateway && make login`.
MEMBERS := console gateway software-company Studio-creators

.PHONY: sync test cov lint types fix build clean $(MEMBERS)

sync:          # một .venv chung ở root, cài cả bốn package editable theo uv.lock
	uv sync --locked

test:          # pytest từng package (ngưỡng coverage của từng package nằm trong pyproject của nó)
	@for d in $(MEMBERS); do echo "== $$d"; $(MAKE) -C $$d test || exit 1; done

cov:
	@for d in $(MEMBERS); do echo "== $$d"; $(MAKE) -C $$d cov || exit 1; done

lint:          # ruff + mypy từng package
	@for d in $(MEMBERS); do echo "== $$d"; $(MAKE) -C $$d lint || exit 1; done

types:
	@for d in $(MEMBERS); do echo "== $$d"; $(MAKE) -C $$d types || exit 1; done

fix:
	@for d in $(MEMBERS); do echo "== $$d"; $(MAKE) -C $$d fix || exit 1; done

build:         # wheel + sdist của cả bốn vào dist/
	uv build --all-packages

clean:
	rm -rf dist build */build */src/*.egg-info

# `make console` = `make -C console` (chạy target mặc định của package đó)
$(MEMBERS):
	$(MAKE) -C $@
