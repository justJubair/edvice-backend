import express from "express";
import { BlogRoutes } from "../modules/blogs/blogs.routes";
import { UniversityRoutes } from "../modules/university/university.routes";

const router = express.Router();

// Define module routes for the LMS API
const moduleRoutes = [
  {
    path: "/blogs",
    route: BlogRoutes,
  },
  {
    path: "/universities",
    route: UniversityRoutes,
  },
];

// Dynamically register module routes
moduleRoutes.forEach((route) => {
  try {
    router.use(route.path, route.route);
  } catch (error) {
    console.error(`Failed to load route ${route.path}:`, error);
  }
});

export default router;
