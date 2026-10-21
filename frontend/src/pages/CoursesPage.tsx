import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createCourse, listCourses } from "../api/courses";

export function CoursesPage() {
  const queryClient = useQueryClient();
  const coursesQuery = useQuery({ queryKey: ["courses"], queryFn: () => listCourses() });

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      createCourse(name.trim(), description.trim() === "" ? null : description.trim()),
    onSuccess: () => {
      setName("");
      setDescription("");
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["courses"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Failed to create course."),
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (name.trim() === "") return;
    createMutation.mutate();
  };

  return (
    <main className="page">
      <nav className="top-nav">
        <Link to="/">Dashboard</Link>
        <span>Courses</span>
      </nav>
      <header className="page-header">
        <h1>Courses</h1>
      </header>
      <section className="grid">
        <form className="card" onSubmit={handleSubmit}>
          <h2>New course</h2>
          <label>
            Name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
            />
          </label>
          <label>
            Description
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={2000}
            />
          </label>
          {error !== null && <p className="error">{error}</p>}
          <button type="submit" disabled={createMutation.isPending || name.trim() === ""}>
            {createMutation.isPending ? "Creating…" : "Create course"}
          </button>
        </form>
        <div className="card">
          <h2>Your courses</h2>
          {coursesQuery.isLoading ? (
            <p className="muted">Loading…</p>
          ) : (coursesQuery.data?.items.length ?? 0) === 0 ? (
            <p className="muted">No courses yet. Create one and upload a course PDF.</p>
          ) : (
            <ul className="item-list">
              {coursesQuery.data?.items.map((course) => (
                <li key={course.id}>
                  <Link to={`/courses/${course.id}`}>{course.name}</Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </main>
  );
}
