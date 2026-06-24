export default function LoadingSpinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const sizeMap = { sm: "1rem", md: "1.5rem", lg: "2rem" };
  
  return (
    <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
      <div
        className="spinner"
        style={{ width: sizeMap[size], height: sizeMap[size] }}
      />
    </div>
  );
}
