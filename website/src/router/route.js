import React from "react";
import { Navigate, Outlet } from "react-router-dom";

const PrivateRoute = () => {
  if (!localStorage.getItem("bearer_token")) return <Navigate to="/login" />;
  return <Outlet />;
};

export default PrivateRoute;
