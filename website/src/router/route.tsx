import React from "react";
import { Navigate, Outlet } from "react-router-dom";
import axios from "axios";
import { useAuth } from "../components/AuthContext";

const PrivateRoute = () => {
  const { checkValid } = useAuth();
  console.log('PrivateRoute...');
  // See if we have a bearer_token in local storage
  if (!localStorage.getItem("bearer_token")) {
    // No - redirect to the login page
    return <Navigate to="/login" />;
  }

  // We have a token, but is it valid?
  console.log('Calling checkValid()');
  checkValid()
  .then (() => {
    console.log("Returned from checkValid()");

    if (!localStorage.getItem("bearer_token")) {
      // No - redirect to the login page
      return <Navigate to="/login" />;
    }
    
    // All good
    return <Outlet />;
  });
};

export default PrivateRoute;
