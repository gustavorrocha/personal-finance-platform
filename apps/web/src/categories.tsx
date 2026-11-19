import { useEffect, useState, type FormEvent } from "react";
import { messages, type Locale } from "./locale";

export type CategoryNode = {
  id: string;
  parent_id: string | null;
  name: string;
};

/** Top-level categories in name order, each with its subcategories. */
export function categoryTree(nodes: CategoryNode[]) {
  return nodes
    .filter((node) => !node.parent_id)
    .map((top) => ({
      ...top,
      children: nodes.filter((node) => node.parent_id === top.id),
    }));
}

/** "Category / Subcategory", or the category name alone. */
export function categoryPath(nodes: CategoryNode[], id: string): string {
  const node = nodes.find((entry) => entry.id === id);
  const parent = nodes.find((entry) => entry.id === node?.parent_id);
  return node ? (parent ? `${parent.name} / ${node.name}` : node.name) : "";
}

async function send(
  method: "POST" | "PUT" | "DELETE",
  path: string,
  body?: object,
) {
  const response = await fetch(`/api/spending/categories${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body && JSON.stringify(body),
    signal: AbortSignal.timeout(5000),
  });
  if (!response.ok) throw new Error();
}

export function CategoriesView({ locale }: { locale: Locale }) {
  const copy = messages[locale];
  const [nodes, setNodes] = useState<CategoryNode[]>();
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<
    "categoriesError" | "categorySaveError" | "categorySaved"
  >();

  useEffect(() => {
    const request = new AbortController();
    void fetch("/api/spending/categories", { signal: request.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        const result = (await response.json()) as {
          categories: CategoryNode[];
        };
        setNodes(result.categories);
      })
      .catch(() => {
        if (!request.signal.aborted) setStatus("categoriesError");
      });
    return () => request.abort();
  }, [revision]);

  async function change(action: () => Promise<void>) {
    setBusy(true);
    setStatus(undefined);
    try {
      await action();
      setStatus("categorySaved");
      setRevision((value) => value + 1);
    } catch {
      setStatus("categorySaveError");
    } finally {
      setBusy(false);
    }
  }

  function save(event: FormEvent<HTMLFormElement>, id?: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const name = String(form.get("name") ?? "").trim();
    const parent = String(form.get("parent") ?? "") || null;
    if (!name) return;
    const target = event.currentTarget;
    void change(async () => {
      await (id
        ? send("PUT", `/${id}`, { name, parent })
        : send("POST", "", { name, parent }));
      if (!id) target.reset();
    });
  }

  function archive(node: CategoryNode) {
    if (
      !window.confirm(copy.archiveCategoryConfirm.replace("{name}", node.name))
    )
      return;
    void change(() => send("DELETE", `/${node.id}`));
  }

  const tree = categoryTree(nodes ?? []);

  function row(node: CategoryNode, isChild: boolean) {
    return (
      <form
        className="category-row"
        key={`${node.id}-${node.name}-${node.parent_id}`}
        onSubmit={(event) => save(event, node.id)}
      >
        <input
          name="name"
          aria-label={copy.categoryName}
          defaultValue={node.name}
          maxLength={60}
          required
          disabled={busy}
        />
        {isChild && (
          <select
            name="parent"
            aria-label={copy.parentCategory}
            defaultValue={node.parent_id ?? ""}
            disabled={busy}
          >
            <option value="">{copy.topLevelCategory}</option>
            {tree.map((top) => (
              <option key={top.id} value={top.id}>
                {top.name}
              </option>
            ))}
          </select>
        )}
        {!isChild && <input type="hidden" name="parent" value="" />}
        <button type="submit" disabled={busy}>
          {copy.saveCategory}
        </button>
        <button type="button" disabled={busy} onClick={() => archive(node)}>
          {copy.archiveCategory}
        </button>
      </form>
    );
  }

  function addForm(parent: string | null, label: string) {
    return (
      <form className="category-row add" onSubmit={(event) => save(event)}>
        <input
          name="name"
          aria-label={label}
          placeholder={label}
          maxLength={60}
          required
          disabled={busy}
        />
        <input type="hidden" name="parent" value={parent ?? ""} />
        <button type="submit" disabled={busy}>
          {copy.addCategory}
        </button>
      </form>
    );
  }

  return (
    <main className="frame" aria-busy={!nodes}>
      <div className="intro">
        <h1>{copy.categories}</h1>
      </div>
      <section className="panel" aria-labelledby="category-editor">
        <h2 id="category-editor">{copy.editCategories}</h2>
        <p>{copy.categoriesHelp}</p>
        {status && <p role="status">{copy[status]}</p>}
        {tree.map((top) => (
          <div className="category-group" key={top.id}>
            {row(top, false)}
            <div className="category-children">
              {top.children.map((child) => row(child, true))}
              {addForm(top.id, copy.newSubcategory)}
            </div>
          </div>
        ))}
        {nodes && addForm(null, copy.newCategory)}
      </section>
    </main>
  );
}
